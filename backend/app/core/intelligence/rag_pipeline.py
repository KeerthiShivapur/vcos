from typing import List, Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any, List, Callable, Awaitable
import json
import uuid
import asyncio
import hashlib

from app.core.intelligence.vector_db import VectorDocument, SearchResult, VectorStore, EmbeddingProvider

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


@dataclass
class LLMMessage:
    role: str
    content: str
    name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMClient:
    def __init__(
        self,
        provider: LLMProvider = LLMProvider.OPENAI,
        api_key: str = None,
        model: str = "gpt-4o-mini",
        base_url: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: int = 60
    ):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._client = None
    
    async def __aenter__(self):
        if self.provider == LLMProvider.OPENAI:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
        elif self.provider == LLMProvider.ANTHROPIC:
            import anthropic
            self._client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client and hasattr(self._client, 'close'):
            await self._client.close()
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = None,
        max_tokens: int = None,
        stop: List[str] = None,
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        if self.provider == LLMProvider.OPENAI:
            return await self._generate_openai(messages, temperature, max_tokens, stop, stream, **kwargs)
        elif self.provider == LLMProvider.ANTHROPIC:
            return await self._generate_anthropic(messages, temperature, max_tokens, stop, stream, **kwargs)
        else:
            return await self._generate_local(prompt, system_prompt, temperature, max_tokens, **kwargs)
    
    async def _generate_openai(
        self,
        messages: List[Dict],
        temperature: float = None,
        max_tokens: int = None,
        stop: List[str] = None,
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        import openai
        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout
        )
        
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            stop=stop,
            stream=stream,
            **kwargs
        )
        
        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            },
            finish_reason=response.choices[0].finish_reason,
            metadata={"provider": "openai", "model": self.model}
        )
    
    async def _generate_anthropic(
        self,
        messages: List[Dict],
        temperature: float = None,
        max_tokens: int = None,
        stop: List[str] = None,
        stream: bool = False,
        **kwargs
    ) -> LLMResponse:
        import anthropic
        client = anthropic.AsyncAnthropic(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout
        )
        
        system_prompt = None
        messages_for_anthropic = []
        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                messages_for_anthropic.append(msg)
        
        response = await client.messages.create(
            model=self.model,
            messages=messages_for_anthropic,
            system=system_prompt,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            stop_sequences=stop,
            stream=stream,
            **kwargs
        )
        
        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            },
            finish_reason=response.stop_reason,
            metadata={"provider": "anthropic", "model": self.model}
        )
    
    async def _generate_local(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = None,
        max_tokens: int = None,
        **kwargs
    ) -> LLMResponse:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
        
        return LLMResponse(
            content="Local LLM not implemented",
            model=self.model,
            metadata={"provider": "local", "model": self.model}
        )
    
    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = None,
        max_tokens: int = None,
        stop: List[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        if self.provider == LLMProvider.OPENAI:
            import openai
            client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
            
            stream = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        
        elif self.provider == LLMProvider.ANTHROPIC:
            import anthropic
            client = anthropic.AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
            
            system_prompt = None
            messages_for_anthropic = []
            for msg in messages:
                if msg["role"] == "system":
                    system_prompt = msg["content"]
                else:
                    messages_for_anthropic.append(msg)
            
            async with anthropic.AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            ).messages.stream(
                model=self.model,
                messages=[m for m in messages if m["role"] != "system"],
                system=system_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        if self.provider == "openai":
            import openai
            client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=texts
            )
            return [d.embedding for d in response.data]
        else:
            raise ValueError(f"Embeddings not supported for provider: {self.provider}")


class RAGPipeline:
    def __init__(
        self,
        vector_store,
        embedder,
        chunker=None,
        retriever=None,
        reranker=None,
        llm_client=None
    ):
        self.vector_store = vector_store
        self.embedder = embedder
        self.chunker = chunker
        self.retriever = retriever
        self.reranker = reranker
        self.llm_client = llm_client
    
    async def ingest_document(
        self,
        document_id: str,
        content: str,
        metadata: Dict = None,
        chunk: bool = True
    ) -> List[VectorDocument]:
        if chunk:
            chunks = self.chunker.chunk_text(content, metadata)
        else:
            chunks = [VectorDocument(
                id=str(uuid.uuid4()),
                document_id=document_id,
                content=content,
                embedding=[],
                metadata=metadata or {},
                chunk_index=0
            )]
        
        texts = [c.content for c in chunks]
        embeddings = await self.embedder.embed(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        await self.vector_store.upsert_documents(chunks)
        return chunks
    
    async def query(
        self,
        query: str,
        k: int = 5,
        hybrid: bool = False,
        rerank: bool = False,
        filter_metadata: Dict = None
    ) -> Dict:
        results = await self.retriever.retrieve(query, k=k * 2 if rerank else k, hybrid=False)
        
        if rerank and self.reranker:
            results = await self.reranker.rerank(query, results)
        
        results = results[:k]
        
        context = "\n\n".join([r.document.content for r in results])
        
        return {
            "query": query,
            "results": results,
            "context": context,
            "answer": await self._generate_answer(query, context) if self.llm_client else None
        }
    
    async def _generate_answer(self, query: str, context: str) -> str:
        if not self.llm_client:
            return "No LLM client configured"
        
        prompt = f"""Answer the question based on the provided context.

Context:
{context}

Question: {query}

Answer:"""
        
        response = await self.llm_client.generate(prompt)
        return response.content


class ConversationManager:
    def __init__(self, max_history: int = 20):
        self.max_history = max_history
        self.conversations: Dict[str, List[LLMMessage]] = {}
    
    def get_conversation(self, conversation_id: str) -> List[LLMMessage]:
        return self.conversations.get(conversation_id, [])
    
    def add_message(self, conversation_id: str, message: LLMMessage):
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []
        
        self.conversations[conversation_id].append(message)
        
        if len(self.conversations[conversation_id]) > self.max_history:
            self.conversations[conversation_id] = self.conversations[conversation_id][-self.max_history:]
    
    def clear_conversation(self, conversation_id: str):
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
    
    def get_context(self, conversation_id: str, max_tokens: int = 4000) -> str:
        messages = self.conversations.get(conversation_id, [])
        context = ""
        for msg in reversed(messages):
            context = f"{msg.role}: {msg.content}\n\n" + context
            if len(context) > max_tokens:
                break
        return context.strip()


class CitationExtractor:
    @staticmethod
    def extract_citations(text: str, sources: List[str]) -> List[Dict]:
        citations = []
        for i, source in enumerate(sources):
            citations.append({
                "index": i + 1,
                "source": source,
                "content": source[:200] + "..." if len(source) > 200 else source
            })
        return citations
    
    @staticmethod
    def format_citations(citations: List[Dict]) -> str:
        if not citations:
            return ""
        
        formatted = "\n\nSources:\n"
        for c in citations:
            formatted += f"[{c['index']}] {c['content']}\n"
        return formatted


class QueryExpander:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
    
    async def expand(self, query: str, num_expansions: int = 3) -> List[str]:
        prompt = f"""Generate {num_expansions} alternative search queries for the following query.
        The queries should be semantically similar but use different wording.
        
        Original query: {query}
        
        Return as JSON array of strings."""
        
        response = await self.llm_client.generate(
            prompt,
            system_prompt="You are a query expansion expert. Generate diverse but semantically equivalent queries.",
            temperature=0.7,
            max_tokens=500
        )
        
        try:
            import json
            expansions = json.loads(response.content)
            return [query] + expansions if isinstance(expansions, list) else [query]
        except:
            return [query]


class FactChecker:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
    
    async def verify_claim(
        self,
        claim: str,
        context: str,
        sources: List[str] = None
    ) -> Dict[str, Any]:
        prompt = f"""Verify the following claim based on the provided context.

Claim: {claim}

Context:
{context}

Sources: {json.dumps(sources) if sources else 'None'}

Return a JSON object with:
- "verified": true/false/uncertain
- "confidence": 0-1
- "explanation": string
- "supporting_evidence": array of strings
- "contradicting_evidence": array of strings"""

        response = await self.llm_client.generate(
            prompt,
            system_prompt="You are a fact-checking expert. Verify claims against provided context.",
            temperature=0.1,
            max_tokens=1000
        )
        
        try:
            return json.loads(response.content)
        except:
            return {
                "verified": "uncertain",
                "confidence": 0.5,
                "explanation": "Failed to parse verification result",
                "supporting_evidence": [],
                "contradicting_evidence": []
            }


class AnswerSynthesizer:
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
    
    async def synthesize(
        self,
        query: str,
        sources: List[str],
        context: str,
        style: str = "comprehensive",
        citations: bool = True
    ) -> str:
        style_prompts = {
            "comprehensive": "Provide a thorough, detailed answer covering all aspects.",
            "concise": "Provide a brief, direct answer.",
            "bullet_points": "Provide answer as bullet points.",
            "executive_summary": "Provide an executive summary with key takeaways."
        }
        
        style_instruction = style_prompts.get(style, style_prompts["comprehensive"])
        
        citation_instruction = "\n\nInclude citations in [1], [2] format." if citations else ""
        
        prompt = f"""Synthesize an answer to the question based on the provided sources.

Style: {style_instruction}

{style_instruction}

Question: {query}

Sources:
{json.dumps([{"index": i+1, "content": s[:500]} for i, s in enumerate(sources)], indent=2)}

Context: {context}

{'' if not citations else 'Include citations in [1], [2] format referencing the source numbers above.'}

Answer:"""
        
        response = await self.llm_client.generate(
            prompt,
            system_prompt="You are an expert research assistant. Synthesize accurate, well-cited answers from provided sources.",
            temperature=0.3,
            max_tokens=2000
        )
        
        return response.content


class SemanticSearchEngine:
    def __init__(
        self,
        vector_store,
        embedder,
        reranker=None,
        hybrid_weight: float = 0.5
    ):
        self.vector_store = vector_store
        self.embedder = embedder
        self.reranker = reranker
        self.hybrid_weight = hybrid_weight
    
    async def search(
        self,
        query: str,
        k: int = 10,
        filters: Dict = None,
        hybrid: bool = True,
        rerank: bool = True
    ) -> List[SearchResult]:
        query_embedding = (await embedder.embed([query]))[0]
        
        if hybrid:
            results = await vector_store.hybrid_search(
                query_text=query,
                query_embedding=query_embedding,
                limit=k,
                alpha=0.5
            )
        else:
            results = await vector_store.search(
                query_embedding=query_embedding,
                limit=k,
                filter_metadata=filters
            )
        
        if reranker and rerank:
            results = await reranker.rerank(query, results)
        
        return results[:k]
    
    async def multi_query_search(
        self,
        queries: List[str],
        k: int = 10,
        deduplicate: bool = True
    ) -> List[SearchResult]:
        all_results = []
        for query in queries:
            results = await self.search(query, k=k)
            all_results.extend(results)
        
        if deduplicate:
            seen = set()
            unique = []
            for r in all_results:
                if r.document.id not in seen:
                    seen.add(r.document.id)
                    unique.append(r)
            return unique[:k]
        
        return all_results[:k]


class SemanticCache:
    def __init__(self, vector_store, embedder, similarity_threshold: float = 0.95):
        self.vector_store = vector_store
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
        self.cache: Dict[str, Any] = {}
    
    async def get(self, query: str) -> Optional[Any]:
        query_embedding = (await self.embedder.embed([query]))[0]
        results = await self.vector_store.search(query_embedding, limit=1, threshold=self.similarity_threshold)
        
        if results and results[0].score >= self.similarity_threshold:
            cached = self.cache.get(results[0].document.id)
            if cached:
                return cached
        return None
    
    async def set(self, query: str, value: Any):
        query_embedding = (await self.embedder.embed([query]))[0]
        results = await self.vector_store.search(query_embedding, limit=1)
        
        if results:
            self.cache[results[0].document.id] = value
    
    async def invalidate(self, query: str = None):
        if query:
            query_embedding = (await self.embedder.embed([query]))[0]
            results = await self.vector_store.search(query_embedding, limit=1)
            if results:
                self.cache.pop(results[0].document.id, None)
        else:
            self.cache.clear()


class SemanticRouter:
    def __init__(self, vector_store, embedder, routes: Dict[str, str]):
        self.vector_store = vector_store
        self.embedder = embedder
        self.routes = routes
        self.route_embeddings: Dict[str, List[float]] = {}
    
    async def initialize(self):
        route_texts = list(self.routes.values())
        embeddings = await self.embedder.embed(route_texts)
        self.route_embeddings = dict(zip(self.routes.keys(), embeddings))
    
    async def route(self, query: str, threshold: float = 0.7) -> Optional[str]:
        query_embedding = (await self.embedder.embed([query]))[0]
        
        best_route = None
        best_score = 0.0
        
        for route_name, route_embedding in self.route_embeddings.items():
            score = self._cosine_similarity(query_embedding, route_embedding)
            if score > best_score and score >= threshold:
                best_score = score
                best_route = route_name
        
        return best_route
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        import numpy as np
        a = np.array(a)
        b = np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))