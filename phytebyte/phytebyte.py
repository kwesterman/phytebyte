from .bioactive_cmpd.negative_samplers import NegativeSampler
from .bioactive_cmpd.clustering import Clusterer
from .bioactive_cmpd.target_input import TargetInput
from .bioactive_cmpd.sources import BioactiveCompoundSource
from .bioactive_cmpd import ModelInputLoader
from .modeling.models import BinaryClassifierModel
from .food_cmpd import FoodCmpdSource, FoodCmpd
from .fingerprinters import Fingerprinter

import logging
from multiprocessing import Pool, cpu_count
from typing import List, Iterator, Tuple
import numpy as np

class PhyteByte():
    logger = logging.getLogger("PhyteByte")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '(%(asctime)s) - %(name)s [%(levelname)s]: %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    fingerprinter = None
    model = None
    # Globals to enable multiprocessing

    def __init__(self,
                 source: BioactiveCompoundSource,
                 target_input: TargetInput,
                 config_file_path: str=None):
        self._target_input = target_input
        self._source = source

        self._config_file_path = config_file_path
        self._negative_sampler = None
        self._positive_clusterer = None

        if config_file_path:
            self._load_config()

    def _load_config(self):
        raise NotImplementedError

    def set_negative_sampler(self,
                             negative_sampler_name: str,
                             fingerprinter: Fingerprinter,
                             *args,
                             **kwargs):
        self._negative_sampler = NegativeSampler.create(
            negative_sampler_name,
            self._source,
            fingerprinter,
            *args, **kwargs)

    def set_positive_clusterer(self,
                               clusterer_name: str,
                               fingerprinter: Fingerprinter,
                               *args,
                               **kwargs):
        self._positive_clusterer = Clusterer.create(
            clusterer_name,
            fingerprinter,
            *args,
            **kwargs)

    @classmethod
    def set_fingerprinter(cls, fingerprinter_name: str, cache=None):
        cls.fingerprinter = Fingerprinter.create(fingerprinter_name,
                                                 cache=cache)

    def train_model(self,
                    model_type: str,
                    neg_sample_size_factor: int,
                    *args,
                    **kwargs):
        binary_classifier_model = BinaryClassifierModel.create(model_type)
        mdl = ModelInputLoader(self._source, self._negative_sampler,
                               self._positive_clusterer, self._target_input,
                               binary_classifier_model.expected_encoding)
        binary_classifier_input = mdl.load(
            neg_sample_size_factor,
            output_fingerprinter=self.fingerprinter)

        binary_classifier_model.train(binary_classifier_input, *args, **kwargs)
        PhyteByte.model = binary_classifier_model

    def train_and_evaluate(
            self,
            model_type: str,
            neg_sample_size_factor: int,
            true_threshold: float,
            *args,
            **kwargs) -> List[float]:
        self.logger.info("Training and evaluating model")
        binary_classifier_model = BinaryClassifierModel.create(model_type)
        self.logger.info("Loading model input.")
        mdl = ModelInputLoader(self._source, self._negative_sampler,
                               self._positive_clusterer, self._target_input,
                               binary_classifier_model.expected_encoding)
        binary_classifier_inputs = mdl.load(
            neg_sample_size_factor, self.fingerprinter)
        self.logger.debug("Done.")
        self.logger.debug("Evaluating model.")
        f1_scores = [binary_classifier_model.evaluate(binary_classifier_input,
                                                      true_threshold,
                                                      *args,
                                                      **kwargs)
                     for binary_classifier_input in binary_classifier_inputs]
        # TODO: We don't really need multiple binary_classifier_inputs here
        self.logger.debug("Done.")
        self.logger.info(f"F1: {f1_scores}")
        PhyteByte.model = binary_classifier_model 
        return f1_scores
    
    def train(self,
              model_type: str,
              neg_sample_size_factor: int,
              true_threshold: float,  
              *args,
              **kwargs) -> List[float]:
        self.logger.info("Training model for production.")
        binary_classifier_model = BinaryClassifierModel.create(model_type)
        self.logger.info("Loading model input.")
        mdl = ModelInputLoader(self._source, self._negative_sampler,
                               self._positive_clusterer, self._target_input,
                               binary_classifier_model.expected_encoding)
        binary_classifier_inputs = mdl.load(
            neg_sample_size_factor, self.fingerprinter)
        self.logger.debug("Done.")
        self.logger.debug("Training.")
        binary_classifier_model.train(
            binary_classifier_inputs[0],
            np.arange(len(binary_classifier_inputs[0]))
        )
        PhyteByte.model = binary_classifier_model
        self.logger.debug("Done.")

    def predict_bioactive_food_cmpd_iter(self,
                                         food_cmpd_source: FoodCmpdSource
                                         ) -> Iterator[Tuple[FoodCmpd, float]]:
        food_cmpd_iter = food_cmpd_source.fetch_all_cmpds()
        with Pool(cpu_count()) as p:
            predicted_cmpd_bioactivity_iter = p.imap(
                self._predict_cmpd_bioactivity,
                food_cmpd_source.fetch_all_cmpd_smiles())
            for food_cmpd, bioactivity_score in zip(
                    food_cmpd_iter, predicted_cmpd_bioactivity_iter):
                if food_cmpd is not None and bioactivity_score is not None:
                    yield food_cmpd, bioactivity_score
    
    def load_positive_compounds(self, model_type: str):
        binary_classifier_model = BinaryClassifierModel.create(model_type)
        self.logger.info("Loading positive compounds")
        mdl = ModelInputLoader(self._source, self._negative_sampler,
                               self._positive_clusterer, self._target_input,
                               binary_classifier_model.expected_encoding)
        positive_compounds = mdl.load_positive_compounds()
        return positive_compounds


    @classmethod
    def _predict_cmpd_bioactivity(cls, food_cmpd_smiles: str
                                  ) -> float:
        encoded_cmpd = cls.fingerprinter.fingerprint_and_encode(
            food_cmpd_smiles, cls.model.expected_encoding)
        if encoded_cmpd is not None:
            return cls.model.calc_score(encoded_cmpd)

    def sort_predicted_bioactive_food_cmpds(self, food_cmpd_source:
                                            FoodCmpdSource
                                            ) -> List[Tuple[FoodCmpd, float]]:
        return sorted(self.predict_bioactive_food_cmpd_iter(food_cmpd_source),
                      key=lambda tup: tup[1],
                      reverse=True)
