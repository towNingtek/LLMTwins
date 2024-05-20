from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.retrieval import create_retrieval_chain
from langchain_community.document_loaders import WikipediaLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.document_loaders import WebBaseLoader

class DocumentLoader():
    def __init__(self, llm):
        self.llm = llm

    def WikipediaLoader(self, query, lang, message):
        OPENAI_EMBEDDING_DEPLOYMENT_NAME = "text-embedding-3-small"
        loader = WikipediaLoader(query = query, lang = lang, load_max_docs = 2)
        # Document loader
        documents = loader.load()

        # Split documents
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        docs = text_splitter.split_documents(documents)

        # Get embeddings
        embeddings = OpenAIEmbeddings(deployment=OPENAI_EMBEDDING_DEPLOYMENT_NAME, chunk_size=1)
        vector = FAISS.from_documents(docs, embeddings)
        retriever = vector.as_retriever()

        context = []
        prompt = ChatPromptTemplate.from_messages([
            ('system', '請以 ' + lang + ' 語系回答:\n\n{context}'),
            ('user', '問題: {input}'),
        ])

        document_chain = create_stuff_documents_chain(self.llm, prompt)
        retrieval_chain = create_retrieval_chain(retriever, document_chain)

        response = retrieval_chain.invoke({
            'input': message,
            'context': context
        })

        return response["answer"]
    
    def WebBaseLoader(self, url, message):
        OPENAI_EMBEDDING_DEPLOYMENT_NAME = "text-embedding-3-small"

        loader = WebBaseLoader(url)

        # Document loader
        documents = loader.load()

        # Split documents
        text_splitter = RecursiveCharacterTextSplitter(chunk_size = 1000, chunk_overlap = 200)
        docs = text_splitter.split_documents(documents)

        # Get embeddings
        embeddings = OpenAIEmbeddings(deployment = OPENAI_EMBEDDING_DEPLOYMENT_NAME, chunk_size = 1)
        vector = FAISS.from_documents(docs, embeddings)
        retriever = vector.as_retriever()

        context = []
        prompt = ChatPromptTemplate.from_messages([
            ('system', '請以正體 (zh_TW) 中文語系回答\'s :\n\n{context}'),
            ('user', '問題: {input}'),
        ])

        document_chain = create_stuff_documents_chain(self.llm, prompt)
        retrieval_chain = create_retrieval_chain(retriever, document_chain)

        response = retrieval_chain.invoke({
            'input': message,
            'context': context
        })

        return response["answer"]