"""Executar na imagem com --network none; nao le .env nem chama Gemini."""
import os
import socket
import unittest
from unittest.mock import patch

from app.lia import indice


class CacheImagemTeste(unittest.TestCase):
    def test_cache_empacotado_confere_com_modelo_e_corpus(self):
        imoveis = indice.carregar()
        vetores = indice.ler_cache(imoveis, 'gemini-embedding-001')
        self.assertIsNotNone(vetores)
        self.assertEqual(len(vetores), len(imoveis))
        self.assertTrue(all(len(v) == indice.DIMENSAO for v in vetores))

    def test_construcao_usa_cache_sem_embedding_ou_rede(self):
        class EmbutidorProibido:
            def documentos(self, *args):
                raise AssertionError('Embedding proibido no smoke')
            def consulta(self, *args):
                raise AssertionError('Embedding proibido no smoke')
        with patch.dict(os.environ, {'GEMINI_EMBEDDING_MODEL': 'gemini-embedding-001'}), \
                patch.object(indice, '_gemini', return_value=EmbutidorProibido()), \
                patch.object(socket, 'create_connection', side_effect=AssertionError('Rede proibida')):
            construido = indice.construir()
        self.assertEqual(construido.origem, 'cache')
        self.assertEqual(construido.modelo, 'gemini-embedding-001')


if __name__ == '__main__':
    unittest.main()
