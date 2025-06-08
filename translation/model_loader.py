"""
Model loading and management for DhinSpeak System
path: /translation/model_loader.py
"""

import asyncio
import logging
import torch
from typing import Optional, Dict, Any
from transformers import MarianMTModel, MarianTokenizer
from symspellpy import SymSpell, Verbosity
import os
from pathlib import Path

from core.config import settings
from core.logging_config import get_error_logger

logger = logging.getLogger(__name__)
error_logger = get_error_logger()

class ModelManager:
    """Manages translation models and spell checkers"""
    
    def __init__(self):
        self.models: Dict[str, MarianMTModel] = {}
        self.tokenizers: Dict[str, MarianTokenizer] = {}
        self.spell_checkers: Dict[str, SymSpell] = {}
        self._ready = False
        
    async def initialize(self):
        """Initialize all models asynchronously"""
        logger.info("Initializing translation models...")
        
        try:
            # Initialize in parallel for faster startup
            await asyncio.gather(
                self._load_translation_models(),
                # self._load_spell_checkers(),
                return_exceptions=True
            )
            
            # Optimize models for inference
            self._optimize_models()
            
            # Warmup models
            await self._warmup_models()
            
            self._ready = True
            logger.info("All models initialized successfully")
            
        except Exception as e:
            error_logger.error(f"Failed to initialize models: {e}")
            raise
            
    async def cleanup(self):
        """Cleanup models and free memory"""
        logger.info("Cleaning up models...")
        
        # Clear models
        self.models.clear()
        self.tokenizers.clear()
        self.spell_checkers.clear()
        
        # Force garbage collection
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        self._ready = False
        logger.info("Models cleanup completed")
        
    def is_ready(self) -> bool:
        """Check if all models are ready"""
        return self._ready
        
    async def _load_translation_models(self):
        """Load translation models"""
        logger.info("Loading translation models...")
        
        # Load Indonesian to English model
        try:
            logger.info(f"Loading ID->EN model: {settings.ID_EN_MODEL_NAME}")
            self.models['id_en'] = MarianMTModel.from_pretrained(settings.ID_EN_MODEL_NAME)
            self.tokenizers['id_en'] = MarianTokenizer.from_pretrained(settings.ID_EN_MODEL_NAME)
            logger.info("ID->EN model loaded")
        except Exception as e:
            error_logger.error(f"Failed to load ID->EN model: {e}")
            raise
            
        # Load English to Indonesian model
        try:
            logger.info(f"Loading EN->ID model: {settings.EN_ID_MODEL_NAME}")
            self.models['en_id'] = MarianMTModel.from_pretrained(settings.EN_ID_MODEL_NAME)
            self.tokenizers['en_id'] = MarianTokenizer.from_pretrained(settings.EN_ID_MODEL_NAME)
            logger.info("EN->ID model loaded")
        except Exception as e:
            error_logger.error(f"Failed to load EN->ID model: {e}")
            raise
            
    # async def _load_spell_checkers(self):
    #     """Load spell checking dictionaries"""
    #     logger.info("Loading spell checkers...")
        
    #     # Load Indonesian spell checker
    #     try:
    #         self.spell_checkers['id'] = SymSpell(
    #             max_dictionary_edit_distance=settings.MAX_EDIT_DISTANCE,
    #             prefix_length=settings.PREFIX_LENGTH
    #         )
            
    #         if os.path.exists(settings.DICTIONARY_ID_PATH):
    #             self.spell_checkers['id'].load_dictionary(
    #                 settings.DICTIONARY_ID_PATH, 
    #                 term_index=0, 
    #                 count_index=1
    #             )
    #             logger.info(f"Indonesian dictionary loaded from {settings.DICTIONARY_ID_PATH}")
    #         else:
    #             logger.warning(f"Indonesian dictionary not found at {settings.DICTIONARY_ID_PATH}")
                
    #     except Exception as e:
    #         error_logger.error(f"Failed to load Indonesian spell checker: {e}")
    #         raise
            
    #     # Load English spell checker
    #     try:
    #         self.spell_checkers['en'] = SymSpell(
    #             max_dictionary_edit_distance=settings.MAX_EDIT_DISTANCE,
    #             prefix_length=settings.PREFIX_LENGTH
    #         )
            
    #         if os.path.exists(settings.DICTIONARY_EN_PATH):
    #             self.spell_checkers['en'].load_dictionary(
    #                 settings.DICTIONARY_EN_PATH, 
    #                 term_index=0, 
    #                 count_index=1
    #             )
    #             logger.info(f"English dictionary loaded from {settings.DICTIONARY_EN_PATH}")
    #         else:
    #             logger.warning(f"English dictionary not found at {settings.DICTIONARY_EN_PATH}")
                
    #     except Exception as e:
    #         error_logger.error(f"Failed to load English spell checker: {e}")
    #         raise
            
    def _optimize_models(self):
        """Optimize models for inference"""
        logger.info("Optimizing models for inference...")
        
        # Disable gradient computation
        torch.set_grad_enabled(False)
        
        # Set models to evaluation mode
        for model in self.models.values():
            model.eval()
            
        # Move to GPU if available
        if torch.cuda.is_available():
            device = torch.device("cuda")
            for key, model in self.models.items():
                try:
                    self.models[key] = model.to(device)
                    logger.info(f"{key} model moved to GPU")
                except Exception as e:
                    logger.warning(f"Failed to move {key} model to GPU: {e}")
                    
        logger.info("Model optimization completed")
        
    async def _warmup_models(self):
        """Warmup models with dummy inputs"""
        logger.info("Warming up models...")
        
        warmup_texts = {
            'id': "Halo, ini adalah tes pemanasan model.",
            'en': "Hello, this is a model warmup test."
        }
        
        try:
            # Warmup ID->EN model
            if 'id_en' in self.models and 'id_en' in self.tokenizers:
                inputs = self.tokenizers['id_en'](warmup_texts['id'], return_tensors="pt", padding=True)
                if torch.cuda.is_available():
                    inputs = {k: v.cuda() for k, v in inputs.items()}
                with torch.no_grad():
                    _ = self.models['id_en'].generate(**inputs, max_length=50)
                logger.info("ID->EN model warmed up")
                
            # Warmup EN->ID model
            if 'en_id' in self.models and 'en_id' in self.tokenizers:
                inputs = self.tokenizers['en_id'](warmup_texts['en'], return_tensors="pt", padding=True)
                if torch.cuda.is_available():
                    inputs = {k: v.cuda() for k, v in inputs.items()}
                with torch.no_grad():
                    _ = self.models['en_id'].generate(**inputs, max_length=50)
                logger.info("EN->ID model warmed up")
                
        except Exception as e:
            logger.warning(f"Model warmup failed: {e}")
            
        logger.info("Model warmup completed")
        
    def get_model_and_tokenizer(self, source_lang: str, target_lang: str):
        """Get model and tokenizer for language pair"""
        if source_lang == 'id' and target_lang == 'en':
            return self.models.get('id_en'), self.tokenizers.get('id_en')
        elif source_lang == 'en' and target_lang == 'id':
            return self.models.get('en_id'), self.tokenizers.get('en_id')
        else:
            return None, None
            
    def get_spell_checker(self, language: str) -> Optional[SymSpell]:
        """Get spell checker for language"""
        return self.spell_checkers.get(language)
        
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about loaded models"""
        return {
            "models_loaded": list(self.models.keys()),
            "spell_checkers_loaded": list(self.spell_checkers.keys()),
            "ready": self._ready,
            "cuda_available": torch.cuda.is_available(),
            "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0
        }
