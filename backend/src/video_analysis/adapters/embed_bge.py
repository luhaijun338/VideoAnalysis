from __future__ import annotations


class BgeM3EmbedAdapter:
    _model = None
    model_name = "BAAI/bge-m3"

    def embed(self, text: str) -> list[float]:
        if type(self)._model is None:
            from FlagEmbedding import BGEM3FlagModel

            type(self)._model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
        out = type(self)._model.encode([text], return_dense=True)
        vec = out["dense_vecs"][0]
        return [float(x) for x in vec.tolist()]
