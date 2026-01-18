from abc import ABC, abstractmethod


class BaseAIProvider(ABC):

    @abstractmethod
    def extract(self, text: str, doc_type: str = 'receipt') -> dict:
        """
        Takes raw text and returns structured JSON
        """
        pass
