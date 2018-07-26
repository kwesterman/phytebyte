from abc import ABC, abstractmethod
import pickle
from typing import List
import os

from phytebyte import ROOT_DIR
from phytebyte.fingerprinters import Fingerprinter


class EncodedSmilesCache(ABC, object):
    @abstractmethod
    def get(smiles: List[str], fp_type: str, encoding: str):
        """ Given a smiles string, a fingerprint type, and a request encoding, retrieve
        the fingerprints encoding associated with the provided smiles.
        """
        pass

    @abstractmethod
    def update(smiles: List[str], fingerprinter: Fingerprinter):
        """ Given a smiles string and a fingerprinter, generate the encoding
        and store it in the relevant data object or database.
        """
        pass

    @abstractmethod
    def write():
        """ Some cache types (e.g. Python objects) may need to be explicitly
        written after being updated, while others (e.g. databases) may not. If
        needed, write the file here, otherwise pass.
        """
        pass

    @abstractmethod
    def clear():
        """ Clear the current cache. """
        pass


class DictEncodedSmilesCache(EncodedSmilesCache):
    def __init__(self, root_dir=ROOT_DIR):
        self._root_dir = root_dir
        self._cache = {}

    def load(self, fp_type, encoding):
        filename = f'{fp_type}_{encoding}.pkl'
        self._filepath = f'{self._root_dir}/.cache/{filename}'
        if filename not in os.listdir(f'{self._root_dir}/.cache'):
            raise Exception(""" Cache has not been created for this fingerprint
                            and encoding combination. """)
        with open(self._filepath, 'rb') as f:
            self._cache[f"{fp_type}_{encoding}"] = pickle.load(f)

    def get(self, smiles, fp_type, encoding):
        return self._cache[f"{fp_type}_{encoding}"].get(smiles)

    def update(self, smiles, fingerprinter, encoding):
        enc = fingerprinter.fingerprint_and_encode(smiles, self.encoding)
        self._cache[f"{fingerprinter.fp_type}_{encoding}"][smiles] = enc

    def write(self):
        with open(self._filepath, 'wb') as f:
            pickle.dump(self._cache, f)

    def clear(self):
        self._cache = {}
