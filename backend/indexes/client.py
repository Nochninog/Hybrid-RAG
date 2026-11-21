import os

import weaviate
from dotenv import load_dotenv


def create_connection():
    load_dotenv()
    return weaviate.connect_to_custom(
        http_host=os.getenv("WEAVIATE_HOST", "localhost"),
        http_port=int(os.getenv("WEAVIATE_HTTP_PORT", "8080")),
        http_secure=False,
        grpc_host=os.getenv("WEAVIATE_HOST", "localhost"),
        grpc_port=int(os.getenv("WEAVIATE_GRPC_PORT", "50051")),
        grpc_secure=False,
    )
