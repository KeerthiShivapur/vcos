"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { 
  Search, 
  Filter, 
  Loader2, 
  Sparkles, 
  FileText, 
  Globe, 
  Brain, 
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  ExternalLink,
  Settings,
  History,
  Star,
  StarOff,
  AlertCircle,
  Info
} from "lucide-react";
import { classNames } from "@/lib/utils";

interface SearchResult {
  id: string;
  title: string;
  content: string;
  source: "documents" | "wiki" | "policies" | "web" | "meetings" | "decisions";
  sourceId: string;
  score: number;
  highlights: string[];
  metadata?: {
    author?: string;
    createdAt?: string;
    updatedAt?: string;
    tags?: string[];
    url?: string;
  };
}

interface RAGResponse {
  answer: string;
  citations: Array<{
    source: string;
    sourceId: string;
    excerpt: string;
    score: number;
  }>;
  confidence: number;
  relatedQuestions: string[];
}

interface SemanticSearchProps {
  organizationId: string;
  onResultSelect?: (result: SearchResult) => void;
  className?: string;
}

export function SemanticSearch({ organizationId, onResultSelect, className }: SemanticSearchProps) {
  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [ragAnswer, setRagAnswer] = useState<RAGResponse | null>(null);
  const [showRag, setShowRag] = useState(false);
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
  const [searchHistory, setSearchHistory] = useState<string[]>([]);
  const [filters, setFilters] = useState({
    sources: ["documents", "wiki", "policies", "meetings", "decisions"] as string[],
    dateRange: "all" as "all" | "week" | "month" | "year",
    sortBy: "relevance" as "relevance" | "date" | "score",
  });
  const [showFilters, setShowFilters] = useState(false);
  const [isLoadingRag, setIsLoadingRag] = useState(false);
  
  const searchInputRef = useRef<HTMLInputElement>(null);
  const resultsContainerRef = useRef<HTMLDivElement>(null);

  // Load search history from localStorage
  useEffect(() => {
    const saved = localStorage.getItem(`vcos_search_history_${organizationId}`);
    if (saved) {
      try {
        setSearchHistory(JSON.parse(saved));
      } catch {}
    }
  }, [organizationId]);

  const saveHistory = useCallback((newQuery: string) => {
    const updated = [newQuery, ...searchHistory.filter(q => q !== newQuery)].slice(0, 10);
    setSearchHistory(updated);
    localStorage.setItem(`vcos_search_history_${organizationId}`, JSON.stringify(updated));
  }, [searchHistory]);

  const performSearch = useCallback(async () => {
    if (!query.trim()) return;
    
    setIsSearching(true);
    try {
      // In production, call the actual API
      // const response = await fetch(`/api/v1/search/semantic`, {
      //   method: "POST",
      //   headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
      //   body: JSON.stringify({ query, organizationId, filters })
      // });
      
      // Simulated results for demo
      await new Promise(resolve => setTimeout(resolve, 500));
      
      const mockResults: SearchResult[] = [
        {
          id: "1",
          title: "Q3 Strategic Planning Document",
          content: "Our Q3 strategic plan focuses on expanding into new markets while optimizing existing operations. Key initiatives include...",
          source: "documents",
          sourceId: "doc-123",
          score: 0.94,
          highlights: ["Q3 strategic plan", "expanding into new markets", "optimizing existing operations"],
          metadata: { author: "Sarah Chen", createdAt: "2024-01-15", tags: ["strategy", "Q3", "planning"] }
        },
        {
          id: "2",
          title: "Remote Work Policy v2.1",
          content: "Updated remote work policy allowing up to 3 days per week remote work with manager approval. Core hours are 10am-3pm...",
          source: "policies",
          sourceId: "pol-456",
          score: 0.89,
          highlights: ["3 days per week remote", "core hours 10am-3pm", "manager approval"],
          metadata: { author: "HR Team", updatedAt: "2024-02-01", tags: ["remote", "policy", "HR"] }
        },
        {
          id: "3",
          title: "Engineering Team Wiki - Architecture Decisions",
          content: "Record of key architecture decisions including microservices migration, database selection, and API gateway choice...",
          source: "wiki",
          sourceId: "wiki-789",
          score: 0.82,
          highlights: ["architecture decisions", "microservices migration", "database selection"],
          metadata: { author: "Tech Lead", createdAt: "2023-11-20", tags: ["architecture", "engineering", "decisions"] }
        },
      ];
      
      setResults(mockResults);
      saveHistory(query);
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setIsSearching(false);
    }
  }, [query, organizationId, filters, searchHistory, saveHistory]);

  const performRagQuery = useCallback(async () => {
    if (!query.trim()) return;
    
    setIsLoadingRag(true);
    try {
      // Simulated RAG response
      await new Promise(resolve => setTimeout(resolve, 800));
      
      const mockRag: RAGResponse = {
        answer: "Based on the company's Q3 strategic plan, the key initiatives for market expansion include: 1) Geographic expansion into APAC markets targeting 15% revenue growth, 2) Product line extension into adjacent verticals with $2M investment, 3) Strategic partnerships with local distributors in target markets. The plan emphasizes maintaining 25%+ operating margins while investing in growth.",
        citations: [
          { source: "documents", sourceId: "doc-123", excerpt: "Q3 strategic plan focuses on expanding into new markets while optimizing existing operations", score: 0.94 },
          { source: "documents", sourceId: "doc-456", excerpt: "APAC market entry strategy with 15% revenue growth target", score: 0.87 },
          { source: "decisions", sourceId: "dec-789", excerpt: "Approved $2M investment for product line extension", score: 0.81 },
        ],
        confidence: 0.89,
        relatedQuestions: [
          "What is the timeline for APAC market entry?",
          "What are the risk factors for market expansion?",
          "How will partnerships be structured?"
        ],
      };
      
      setRagAnswer(mockRag);
      setShowRag(true);
    } catch (err) {
      console.error("RAG query failed:", err);
    } finally {
      setIsLoadingRag(false);
    }
  }, [query]);

  const handleSearch = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    performSearch();
  }, [performSearch]);

  const handleRagQuery = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    performRagQuery();
  }, [performRagQuery]);

  const toggleSource = useCallback((source: string) => {
    setSelectedSources(prev => {
      const next = new Set(prev);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  }, []);

  const clearResults = useCallback(() => {
    setResults([]);
    setRagAnswer(null);
    setShowRag(false);
    setQuery("");
  }, []);

  const copyAnswer = useCallback(() => {
    if (ragAnswer) {
      navigator.clipboard.writeText(ragAnswer.answer);
    }
  }, [ragAnswer]);

  const getSourceIcon = (source: string) => {
    switch (source) {
      case "documents": return <FileText className="h-4 w-4" />;
      case "wiki": return <Globe className="h-4 w-4" />;
      case "policies": return <FileText className="h-4 w-4" />;
      case "meetings": return <FileText className="h-4 w-4" />;
      case "decisions": return <Brain className="h-4 w-4" />;
      default: return <FileText className="h-4 w-4" />;
    }
  };

  const getSourceLabel = (source: string) => {
    const labels: Record<string, string> = {
      documents: "Documents",
      wiki: "Wiki",
      policies: "Policies",
      meetings: "Meetings",
      decisions: "Decisions",
      web: "Web",
    };
    return labels[source] || source;
  };

  const formatScore = (score: number) => (score * 100).toFixed(0) + "%";

  return (
    <div className={classNames("flex flex-col h-full bg-canvas rounded-xl border border-line overflow-hidden", className)}>
      {/* Search Header */}
      <div className="flex flex-col gap-4 p-4 border-b border-line bg-canvas/50">
        {/* Search Input */}
        <form onSubmit={handleSearch} className="relative">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
            <input
              ref={searchInputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask anything about your company... (e.g., 'What is our Q3 strategy?')"
              className="w-full h-12 pl-12 pr-40 rounded-xl border border-line bg-surface text-base text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
              autoFocus
            />
            <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
              <button
                type="button"
                onClick={performRagQuery}
                disabled={isLoadingRag || !query.trim()}
                className={classNames(
                  "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                  "bg-brand text-white hover:bg-brand-strong",
                  !query.trim() && "opacity-50 cursor-not-allowed"
                )}
              >
                {isLoadingRag ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    Thinking...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" />
                    Ask AI
                  </>
                )}
              </button>
              <button
                type="submit"
                disabled={isSearching || !query.trim()}
                className={classNames(
                  "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                  "bg-canvas border border-line text-ink hover:bg-muted",
                  !query.trim() && "opacity-50 cursor-not-allowed"
                )}
              >
                {isSearching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Search"
                )}
              </button>
            </div>
          </form>

          {/* Filters */}
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={classNames(
                "px-3 py-1.5 rounded-lg text-sm font-medium transition-colors flex items-center gap-1",
                showFilters ? "bg-brand text-white" : "bg-canvas border border-line text-ink hover:bg-muted"
              )}
            >
              <Filter className="h-4 w-4" />
              Filters
              {Object.values(filters.sources).filter(s => filters.sources.includes(s)).length < 5 && (
                <span className="px-1.5 py-0.5 rounded text-xs bg-brand/20 text-brand">
                  {filters.sources.length}
                </span>
              )}
              <ChevronDown className="h-4 w-4" />
            </button>

            <div className="flex-1" />
            <div className="flex items-center gap-1">
              <button
                onClick={() => setShowRag(!showRag)}
                className={classNames(
                  "p-2 rounded-lg transition-colors",
                  showRag ? "bg-brand text-white" : "bg-canvas border border-line text-ink hover:bg-muted"
                )}
                title={showRag ? "Hide AI Answer" : "Show AI Answer"}
              >
                <Brain className="h-5 w-5" />
              </button>
              <button
                onClick={clearResults}
                className="p-2 rounded-lg transition-colors bg-canvas border border-line text-ink hover:bg-muted"
                title="Clear Results"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Advanced Filters Panel */}
          {showFilters && (
            <div className="p-4 border-t border-line bg-canvas/50 animate-slide-down">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <label className="block text-xs font-medium text-muted mb-2">Sources</label>
                  <div className="space-y-1">
                    {["documents", "wiki", "policies", "meetings", "decisions"].map(source => (
                      <label key={source} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={filters.sources.includes(source)}
                          onChange={(e) => setFilters(prev => ({
                            ...prev,
                            sources: e.target.checked 
                              ? [...prev.sources, source]
                              : prev.sources.filter(s => s !== source)
                          }))}
                          className="rounded border-line text-brand focus:ring-brand"
                        />
                        <span className="text-sm flex items-center gap-1">
                          {getSourceIcon(source)}
                          {getSourceLabel(source)}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted mb-2">Date Range</label>
                  <select
                    value={filters.dateRange}
                    onChange={(e) => setFilters(prev => ({ ...prev, dateRange: e.target.value as any }))}
                    className="w-full px-3 py-2 rounded-lg border border-line bg-surface text-sm text-ink focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  >
                    <option value="all">All Time</option>
                    <option value="week">Past Week</option>
                    <option value="month">Past Month</option>
                    <option value="year">Past Year</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted mb-2">Sort By</label>
                  <select
                    value={filters.sortBy}
                    onChange={(e) => setFilters(prev => ({ ...prev, sortBy: e.target.value as any }))}
                    className="w-full px-3 py-2 rounded-lg border border-line bg-surface text-sm text-ink focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  >
                    <option value="relevance">Relevance</option>
                    <option value="date">Date (Newest)</option>
                    <option value="score">Confidence Score</option>
                  </select>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* AI Answer Panel */}
      {showRag && ragAnswer && (
        <div className="p-4 border-b border-line bg-brand/5 animate-slide-down">
          <div className="flex items-start justify-between gap-4 mb-4">
            <div className="flex items-center gap-2">
              <Brain className="h-5 w-5 text-brand" />
              <span className="font-medium text-ink">AI Answer</span>
              <span className={classNames(
                "px-2 py-0.5 rounded text-xs font-medium",
                ragAnswer.confidence > 0.8 ? "bg-emerald-100 text-emerald-700" :
                ragAnswer.confidence > 0.6 ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
              )}>
                {Math.round(ragAnswer.confidence * 100)}% confidence
              </span>
            </div>
            <div className="flex items-center gap-1 ml-auto">
              <button
                onClick={copyAnswer}
                className="p-1.5 rounded hover:bg-brand/10 text-brand hover:bg-brand/10 transition-colors"
                title="Copy answer"
              >
                <Copy className="h-4 w-4" />
              </button>
              <button
                onClick={() => setShowRag(false)}
                className="p-1.5 rounded hover:bg-muted text-muted hover:text-ink transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
          
          <div className="prose prose-sm max-w-none text-ink mb-4">
            {ragAnswer.answer.split("\n").map((paragraph, i) => (
              <p key={i} className="mb-2">{paragraph}</p>
            ))}
          </div>

          {/* Citations */}
          {ragAnswer.citations.length > 0 && (
            <div className="border-t border-brand/20 pt-4">
              <h4 className="text-sm font-medium text-muted mb-2 flex items-center gap-1">
                <Star className="h-3 w-3" />
                Sources ({ragAnswer.citations.length})
              </h4>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {ragAnswer.citations.map((citation, index) => (
                  <div
                    key={index}
                    className="p-3 rounded-lg bg-canvas border border-line hover:bg-muted transition-colors cursor-pointer"
                    onClick={() => onResultSelect?.({
                      id: citation.sourceId,
                      title: citation.source,
                      content: citation.excerpt,
                      source: citation.source as any,
                      sourceId: citation.sourceId,
                      score: citation.score,
                      highlights: [],
                    })}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-brand/10 text-brand">
                            {citation.source.toUpperCase()}
                          </span>
                          <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700">
                            {formatScore(citation.score)}
                          </span>
                        </div>
                        <p className="text-sm text-ink line-clamp-2">{citation.excerpt}</p>
                      </div>
                      <ExternalLink className="h-4 w-4 text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Related Questions */}
          {ragAnswer.relatedQuestions.length > 0 && (
            <div className="mt-4 pt-4 border-t border-brand/20">
              <h4 className="text-sm font-medium text-muted mb-2">Related Questions</h4>
              <div className="flex flex-wrap gap-2">
                {ragAnswer.relatedQuestions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => { setQuery(q); performRagQuery(); }}
                    className="px-3 py-1.5 rounded-full text-xs text-brand border border-brand/30 hover:bg-brand/5 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Search Results */}
      <div className="flex-1 overflow-y-auto p-4">
        {isSearching && (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <Loader2 className="h-8 w-8 animate-spin text-brand mx-auto mb-3" />
              <p className="text-muted">Searching across your company knowledge...</p>
            </div>
          </div>
        )}

        {!isSearching && !showRag && results.length === 0 && !query && (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Brain className="h-16 w-16 text-muted/30 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-muted mb-2">Search Your Company Knowledge</h3>
            <p className="text-faint max-w-md mx-auto">
              Ask questions in natural language or search for documents, policies, decisions, and more.
            </p>
            <div className="flex flex-wrap gap-2 justify-center mt-6">
              {[
                "What is our Q3 strategy?",
                "Remote work policy",
                "Architecture decisions",
                "Latest board decisions",
              ].map((suggestion, i) => (
                <button
                  key={i}
                  onClick={() => { setQuery(suggestion); performSearch(); }}
                  className="px-4 py-2 rounded-full text-sm text-brand border border-brand/30 hover:bg-brand/5 transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {!isSearching && results.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium text-ink">
                {results.length} result{results.length !== 1 ? "s" : ""} for "{query}"
              </h3>
              <select
                value={filters.sortBy}
                onChange={(e) => setFilters(prev => ({ ...prev, sortBy: e.target.value as any }))}
                className="px-3 py-1.5 rounded-lg border border-line bg-surface text-sm text-ink focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              >
                <option value="relevance">Relevance</option>
                <option value="date">Date (Newest)</option>
                <option value="score">Score</option>
              </select>
            </div>

            <div className="space-y-3 max-h-[calc(100vh-300px)] overflow-y-auto" ref={resultsContainerRef}>
              {results.map((result, index) => (
                <div
                  key={result.id}
                  className="group p-4 rounded-xl border border-line bg-canvas hover:bg-muted/50 transition-colors cursor-pointer"
                  onClick={() => onResultSelect?.(result)}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={classNames(
                          "px-2 py-0.5 rounded text-xs font-medium",
                          result.source === "documents" && "bg-blue-100 text-blue-700",
                          result.source === "wiki" && "bg-green-100 text-green-700",
                          result.source === "policies" && "bg-red-100 text-red-700",
                          result.source === "meetings" && "bg-purple-100 text-purple-700",
                          result.source === "decisions" && "bg-amber-100 text-amber-700",
                        )}>
                          {getSourceIcon(result.source)}
                          {getSourceLabel(result.source)}
                        </span>
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700">
                          {formatScore(result.score)}
                        </span>
                        {result.metadata?.tags && (
                          <div className="flex items-center gap-1 mt-1 flex-wrap">
                            {result.metadata.tags.slice(0, 3).map(tag => (
                              <span key={tag} className="px-1.5 py-0.5 rounded text-[10px] text-muted bg-muted">
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <h4 className="font-medium text-ink mb-1 group-hover:text-brand transition-colors">
                        {result.title}
                      </h4>
                      <div className="text-sm text-muted line-clamp-2 mb-2">
                        {result.highlights.map((h, i) => (
                          <span key={i} className="bg-amber-100 text-amber-800 px-1 rounded mx-0.5">
                            {h}
                          </span>
                        ))}
                        {result.content.length > 200 
                          ? result.content.slice(0, 200) + "..."
                          : result.content}
                      </div>
                      {result.metadata && (
                        <div className="flex items-center gap-3 mt-2 text-xs text-faint">
                          {result.metadata.author && (
                            <span className="flex items-center gap-1">
                              <User className="h-3 w-3" />
                              {result.metadata.author}
                            </span>
                          )}
                          {result.metadata.createdAt && (
                            <span className="flex items-center gap-1">
                              <History className="h-3 w-3" />
                              {new Date(result.metadata.createdAt).toLocaleDateString()}
                            </span>
                          )}
                          {result.metadata.updatedAt && result.metadata.updatedAt !== result.metadata.createdAt && (
                            <span className="flex items-center gap-1">
                              <Info className="h-3 w-3" />
                              Updated {new Date(result.metadata.updatedAt).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className={classNames(
                        "px-2 py-1 rounded text-xs font-mono font-medium",
                        result.score > 0.8 ? "bg-emerald-100 text-emerald-700" :
                        result.score > 0.6 ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
                      )}>
                        {formatScore(result.score)}
                      </span>
                      <button
                        onClick={(e) => { e.stopPropagation(); onResultSelect?.(result); }}
                        className="p-2 rounded-lg text-muted hover:bg-muted hover:text-brand transition-colors"
                        title="Open result"
                      >
                        <ExternalLink className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {!isSearching && !showRag && results.length === 0 && query && (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <AlertCircle className="h-12 w-12 text-muted/30 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-muted mb-2">No results found</h3>
              <p className="text-faint max-w-md mx-auto">
                Try different keywords or use the AI to ask a question instead.
              </p>
              <button
                onClick={performRagQuery}
                className="mt-4 px-6 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-strong transition-colors"
              >
                <Sparkles className="h-4 w-4 inline mr-2" />
                Ask AI Instead
              </button>
            </div>
          )}
        </div>

        {/* Search History Sidebar (collapsible) */}
        {searchHistory.length > 0 && (
          <div className="border-l border-line bg-canvas/50 w-64 flex-shrink-0 hidden lg:block">
            <div className="p-3 border-b border-line">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-faint">Recent Searches</h4>
            </div>
            <div className="p-3 space-y-2 max-h-[calc(100vh-300px)] overflow-y-auto">
              {searchHistory.slice(0, 10).map((hist, i) => (
                <button
                  key={i}
                  onClick={() => { setQuery(hist); performSearch(); }}
                  className="w-full text-left p-2 rounded-lg text-sm text-muted hover:bg-muted hover:text-ink transition-colors text-left truncate"
                >
                  {hist}
                </button>
              ))}
              <button
                onClick={() => {
                  setSearchHistory([]);
                  localStorage.removeItem(`vcos_search_history_${organizationId}`);
                }}
                className="w-full text-left px-3 py-2 text-xs text-red-500 hover:bg-red-50 rounded-lg transition-colors"
              >
                Clear history
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}