from dotenv import load_dotenv
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

# Load environment variables
load_dotenv()

# Load documents from a directory (you can change this path as needed)
documents = SimpleDirectoryReader("sample_tos").load_data()
# Create an index from the documents
index = VectorStoreIndex.from_documents(documents)

# Create a retriever to fetch relevant documents
retriever = index.as_retriever(retrieval_mode='similarity', k=3)


# Create a query engine
query_engine = index.as_query_engine()

# create and query RAG
def get_rag_response(query: str):
    # Execute the query and return the response
    response = query_engine.query(query)
    return response

async def get_rag_data(query: str):
    print("\n" + "="*50 + "\n")
    print("getting rag response")
    print(f"Query: {query}")
    # Retrieve relevant documents
    relevant_docs = retriever.retrieve(query)

    print(f"Number of relevant documents: {len(relevant_docs)}")
    print("\n" + "="*50 + "\n")

    response = ""   

    for i, doc in enumerate(relevant_docs):
        response += "\n" + "="*50 + "\n"
        response += f"Query: {query}\n"
        response += f"Text: {doc.node.get_content()[:500]}...\n"  # Print first 200 characters
        response += f"Score: {doc.score}\n"
        response += "\n" + "="*50 + "\n"

    return response
