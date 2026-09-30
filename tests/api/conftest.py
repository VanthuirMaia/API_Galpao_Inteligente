import os

# segredo de teste (mínimo de 32 caracteres); lido pela API a cada chamada
os.environ.setdefault("JWT_SECRET", "segredo-de-teste-com-mais-de-32-caracteres")
