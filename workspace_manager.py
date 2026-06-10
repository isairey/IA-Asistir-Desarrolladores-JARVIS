"""Workspace manager module for handling file operations and codebase management."""

# pylama:ignore=E501,C901,E125,E251
import hashlib
import logging
import math
import mmap
import os
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


@dataclass
class Document:
    path: str
    content: str
    term_freqs: Counter
    length: int


class BM25Search:

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1  # Term frequency scaling parameter
        self.b = b  # Length normalization parameter
        self.documents: Dict[str, Document] = {}
        self.avg_doc_length: float = 0
        self.total_docs: int = 0
        self.idf_cache: Dict[str, float] = {}
        self.tokenizer_pattern = re.compile(r"\w+|[^\w\s]")
        self._lock = threading.Lock()

        # Initialize logging
        self.logger = logging.getLogger("BM25Search")
        self.logger.setLevel(logging.DEBUG)

    def preprocess(self, text: str) -> List[str]:
        """Tokenize and normalize text"""
        # Convert to lowercase and tokenize
        tokens = self.tokenizer_pattern.findall(text.lower())
        # Filter out single character tokens except if they're special
        # characters
        return [t for t in tokens if len(t) > 1 or not t.isalnum()]

    def add_document(self, path: str, content: str) -> None:
        """Add a document to the search index"""
        with self._lock:
            # Preprocess content
            tokens = self.preprocess(content)
            # Create document object
            doc = Document(
                path=path,
                content=content,
                term_freqs=Counter(tokens),
                length=len(tokens),
            )

            # Update index
            self.documents[path] = doc

            # Update average document length
            self.total_docs = len(self.documents)
            total_length = sum(doc.length for doc in self.documents.values())
            self.avg_doc_length = (total_length / self.total_docs
                                   if self.total_docs > 0 else 0)

            # Clear IDF cache as it needs to be recalculated
            self.idf_cache.clear()

    def remove_document(self, path: str) -> None:
        """Remove a document from the search index"""
        with self._lock:
            if path in self.documents:
                del self.documents[path]
                self.total_docs = len(self.documents)
                if self.total_docs > 0:
                    total_length = sum(doc.length
                                       for doc in self.documents.values())
                    self.avg_doc_length = total_length / self.total_docs
                else:
                    self.avg_doc_length = 0
                self.idf_cache.clear()

    def _calculate_idf(self, term: str) -> float:
        """Calculate Inverse Document Frequency for a term"""
        if term in self.idf_cache:
            return self.idf_cache[term]

        # Count documents containing the term
        doc_freq = sum(1 for doc in self.documents.values()
                       if term in doc.term_freqs)

        # Calculate IDF with smoothing
        idf = math.log(1 + (self.total_docs - doc_freq + 0.5) /
                       (doc_freq + 0.5))
        self.idf_cache[term] = idf
        return idf

    def search(self,
               query: str,
               top_k: int = 10) -> List[Tuple[str, float, str]]:
        """Search for documents matching the query"""
        start_time = time.time()
        self.logger.debug(f"Starting search for query: {query}")

        # Preprocess query
        query_terms = self.preprocess(query)
        scores: Dict[str, float] = defaultdict(float)

        # Calculate scores for each document
        for path, doc in self.documents.items():
            score = 0.0
            doc_len_norm = 1 - self.b + self.b * \
                (doc.length / self.avg_doc_length)

            for term in query_terms:
                if term in doc.term_freqs:
                    tf = doc.term_freqs[term]
                    idf = self._calculate_idf(term)

                    # BM25 scoring formula
                    term_score = (idf * tf * (self.k1 + 1) /
                                  (tf + self.k1 * doc_len_norm))
                    score += term_score

            if score > 0:
                scores[path] = score

        # Sort results by score
        results = []
        for path, score in sorted(scores.items(),
                                  key=lambda x: x[1],
                                  reverse=True)[:top_k]:
            doc = self.documents[path]
            # Get a relevant snippet from the content
            snippet = self._get_relevant_snippet(doc.content, query_terms)
            results.append((path, score, snippet))

        elapsed_time = time.time() - start_time
        self.logger.info(
            f"Search completed in {elapsed_time:.3f}s, found {len(results)} results"
        )
        return results

    def _get_relevant_snippet(self,
                              content: str,
                              query_terms: List[str],
                              snippet_size: int = 200) -> str:
        """Extract a relevant snippet from the content containing query terms"""
        # Find the best window containing query terms
        lines = content.split("\n")
        best_score = 0
        best_snippet = ""

        for i in range(len(lines)):
            window = " ".join(lines[max(0, i - 2):min(len(lines), i + 3)])
            if len(window) > snippet_size * 2:
                continue

            score = sum(1 for term in query_terms
                        if term.lower() in window.lower())
            if score > best_score:
                best_score = score
                best_snippet = window

        if not best_snippet and lines:
            # Fallback to first few lines if no relevant snippet found
            best_snippet = " ".join(lines[:5])

        # Truncate and add ellipsis if needed
        if len(best_snippet) > snippet_size:
            best_snippet = best_snippet[:snippet_size] + "..."

        return best_snippet


class WorkspaceManager:
    # File size thresholds and constants
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    PREVIEW_SIZE = 10 * 1024  # 10KB for previews
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks for large file reading
    LAZY_LOAD_THRESHOLD = 1000  # Number of files before switching to lazy loading
    MAX_CACHE_SIZE = 100 * 1024 * 1024  # 100MB max cache size
    MAX_CACHE_ENTRIES = 1000  # Maximum number of cached files
    INDEXING_CHUNK_SIZE = 5 * 1024 * 1024  # 5MB chunks for indexing
    LARGE_FILE_THRESHOLD = 1 * 1024 * 1024  # 1MB threshold for large files

    # File type configurations
    BINARY_EXTENSIONS = {".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin"}
    SKIP_EXTENSIONS = {".db", ".log", ".cache"} | BINARY_EXTENSIONS
    SKIP_FOLDERS = {
        ".git",
        "node_modules",
        "__pycache__",
        "venv",
        ".venv",
        "env",
        ".env",
        "dist",
        "build",
        "target",
        "vendor",
        ".idea",
        ".vscode",
        "coverage",
        ".next",
        ".nuxt",
        ".output",
        "tmp",
        "temp",
    }

    # Language-specific patterns for better context understanding
    LANGUAGE_PATTERNS = {
        "python": {
            "imports":
            r"^(?:from|import)\s+[\w.]+(?:\s+(?:as|import)\s+[\w.]+)*",
            "classes": r"^class\s+\w+(?:\(.*?\))?:",
            "functions": r"^def\s+\w+\s*\([^)]*\)\s*(?:->\s*[\w\[\],\s]+)?:",
        },
        "javascript": {
            "imports": r'^(?:import|export)\s+.*?(?:from\s+[\'"].*?[\'"])?;?$',
            "classes":
            r"^(?:export\s+)?class\s+\w+(?:\s+extends\s+\w+)?(?:\s+implements\s+\w+(?:\s*,\s*\w+)*)?",
            "functions": r"^(?:async\s+)?function\s*\w*\s*\([^)]*\)",
        },
    }

    def __init__(self, workspace_root: str):
        """Initialize workspace manager with enhanced features"""
        self.workspace_root = workspace_root
        os.makedirs(workspace_root, exist_ok=True)

        # Initialize enhanced logging
        self.logger = logging.getLogger("WorkspaceManager")
        self.logger.setLevel(logging.DEBUG)

        # Setup console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)

        # Setup file handler
        try:
            log_file = os.path.join(workspace_root, "workspace_manager.log")
            if os.path.exists(log_file):
                try:
                    os.remove(log_file)
                except Exception as e:
                    print(f"Failed to delete old log file: {e}")

            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_format = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to setup file logging: {e}")

        self.logger.info(
            f"Initializing WorkspaceManager with root: {workspace_root}")

        # Initialize BM25 search
        self.search_index = BM25Search()
        self.logger.info("Initialized BM25 search index")

        # Enhanced caching system with LRU and size tracking
        self._content_cache: Dict[str, Tuple[str, float, int]] = {}
        self._structure_cache: Dict[str, Tuple[List[dict], float]] = {}
        self._chunk_cache: Dict[str, Dict[int, str]] = {}
        self._symbol_cache: Dict[str, Dict[str, List[Tuple[int, str]]]] = {}
        self._dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        self._file_index: Dict[str, Dict[str, Any]] = {}
        self._cache_size = 0
        self._cache_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._gitignore_patterns: List[str] = []

        self.logger.debug("Initialized caching systems and thread pool")
        self._load_gitignore()

    def _update_cache_size(self, path: str, content: str, is_add: bool = True):
        """Track cache size with thread safety"""
        with self._cache_lock:
            size = len(content.encode("utf-8"))
            if is_add:
                self._cache_size += size
                # Implement LRU cache eviction if needed
                while (self._cache_size > self.MAX_CACHE_SIZE
                       or len(self._content_cache) > self.MAX_CACHE_ENTRIES):
                    oldest_path = next(iter(self._content_cache))
                    oldest_content = self._content_cache.pop(oldest_path)[0]
                    self._cache_size -= len(oldest_content.encode("utf-8"))
            else:
                self._cache_size -= size

    def _index_file(self,
                    file_path: str,
                    content: Optional[str] = None) -> Dict[str, Any]:
        """Index file contents for faster searching and context understanding"""
        if not content:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                return {}  # Skip binary files

        ext = Path(file_path).suffix.lower()
        lang = "python" if ext == ".py" else "javascript" if ext == ".js" else None

        index = {
            "symbols": defaultdict(list),
            "imports": set(),
            "size": os.path.getsize(file_path),
            "hash": hashlib.md5(content.encode()).hexdigest(),
            "last_modified": os.path.getmtime(file_path),
            "language": lang,
        }

        if lang and lang in self.LANGUAGE_PATTERNS:
            patterns = self.LANGUAGE_PATTERNS[lang]
            for symbol_type, pattern in patterns.items():
                for i, line in enumerate(content.splitlines(), 1):
                    if re.match(pattern, line.strip()):
                        index["symbols"][symbol_type].append((i, line.strip()))
                        if symbol_type == "imports":
                            index["imports"].add(line.strip())

        self._file_index[file_path] = index
        return index

    def _analyze_dependencies(
            self, files_content: Dict[str, str]) -> Dict[str, Set[str]]:
        """Analyze and cache file dependencies"""
        dependencies = defaultdict(set)
        for file_path, content in files_content.items():
            if file_path not in self._file_index:
                self._index_file(file_path, content)

            if file_path in self._file_index:
                index = self._file_index[file_path]
                if index.get("language") == "python":
                    for imp in index.get("imports", set()):
                        # Convert import statement to module path
                        match = re.match(r"^from\s+([\w.]+)\s+import", imp)
                        if match:
                            module = match.group(1)
                            dependencies[file_path].add(
                                module.replace(".", "/") + ".py")

        return dependencies

    def _get_file_content(self,
                          file_path: str,
                          start_chunk: int = 0,
                          num_chunks: int = 1) -> str:
        """Enhanced file content retrieval with chunked reading and caching"""
        try:
            file_size = os.path.getsize(file_path)
            self.logger.debug(
                f"Reading file {file_path} (size: {file_size} bytes)")

            # For small files, use content cache
            if file_size < self.LARGE_FILE_THRESHOLD:
                if file_path in self._content_cache:
                    content, mtime, size = self._content_cache[file_path]
                    if os.path.getmtime(
                            file_path) == mtime and size == file_size:
                        self.logger.debug(f"Cache hit for {file_path}")
                        return content

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        self._update_cache_size(file_path, content)
                        self._content_cache[file_path] = (
                            content,
                            os.path.getmtime(file_path),
                            file_size,
                        )

                        # Add to search index if it's a new file
                        if file_path not in self.search_index.documents:
                            try:
                                rel_path = os.path.relpath(
                                    file_path, self.workspace_root)
                                self.search_index.add_document(
                                    rel_path, content)
                                self.logger.debug(
                                    f"Added {rel_path} to search index")
                            except Exception as e:
                                self.logger.warning(
                                    f"Failed to add {file_path} to search index: {e}"
                                )

                        return content
                except UnicodeDecodeError:
                    with open(file_path, "r", encoding="latin-1") as f:
                        content = f.read()
                        self._update_cache_size(file_path, content)
                        self._content_cache[file_path] = (
                            content,
                            os.path.getmtime(file_path),
                            file_size,
                        )

                        # Add to search index if it's a new file
                        if file_path not in self.search_index.documents:
                            try:
                                rel_path = os.path.relpath(
                                    file_path, self.workspace_root)
                                self.search_index.add_document(
                                    rel_path, content)
                                self.logger.debug(
                                    f"Added {rel_path} to search index")
                            except Exception as e:
                                self.logger.warning(
                                    f"Failed to add {file_path} to search index: {e}"
                                )

                        return content

            # For large files, use chunk cache and mmap for efficiency
            if file_path not in self._chunk_cache:
                self._chunk_cache[file_path] = {}

            chunks = []
            for i in range(start_chunk, start_chunk + num_chunks):
                if i in self._chunk_cache[file_path]:
                    chunks.append(self._chunk_cache[file_path][i])
                    continue

                offset = i * self.CHUNK_SIZE
                if offset >= file_size:
                    break

                try:
                    with open(file_path, "rb") as f:
                        with mmap.mmap(f.fileno(), 0,
                                       access=mmap.ACCESS_READ) as mm:
                            mm.seek(offset)
                            chunk_bytes = mm.read(self.CHUNK_SIZE)
                            try:
                                chunk = chunk_bytes.decode("utf-8")
                            except UnicodeDecodeError:
                                chunk = chunk_bytes.decode("latin-1")
                            self._chunk_cache[file_path][i] = chunk
                            chunks.append(chunk)
                except (ValueError, OSError) as e:
                    self.logger.error(
                        f"Error reading file {file_path} with mmap: {str(e)}")
                    # Fallback to regular file reading
                    with open(file_path, "r", encoding="utf-8") as f:
                        f.seek(offset)
                        chunk = f.read(self.CHUNK_SIZE)
                        self._chunk_cache[file_path][i] = chunk
                        chunks.append(chunk)

            content = "".join(chunks)

            # Add to search index if it's a new file
            if content and file_path not in self.search_index.documents:
                try:
                    rel_path = os.path.relpath(file_path, self.workspace_root)
                    self.search_index.add_document(rel_path, content)
                    self.logger.debug(f"Added {rel_path} to search index")
                except Exception as e:
                    self.logger.warning(
                        f"Failed to add {file_path} to search index: {e}")

            return content

        except (IOError, UnicodeDecodeError) as e:
            self.logger.error(f"Error reading file {file_path}: {str(e)}")
            return ""

    def get_workspace_files(self,
                            workspace_dir: str,
                            query: str = None) -> Dict[str, str]:
        """Enhanced workspace file retrieval with smart filtering and parallel processing"""
        start_time = time.time()
        self.logger.info(f"Getting workspace files for: {workspace_dir}" +
                         (f" with query: {query}" if query else ""))

        files_content = {}
        all_files = []

        try:
            # Collect all files with parallel processing
            self.logger.debug("Starting parallel file scan...")
            all_files = self._parallel_scan(workspace_dir)
            self.logger.info(f"Found {len(all_files)} files to process")

            # If no query, only include small files and files in root directory
            if not query:
                self.logger.debug(
                    "No query provided, selecting root and small files...")
                for file_path, rel_path in all_files:
                    try:
                        if (os.path.dirname(rel_path) == ""
                                or os.path.getsize(file_path)
                                < self.LARGE_FILE_THRESHOLD):
                            content = self._get_file_content(file_path)
                            if content:
                                # Truncate content for context
                                files_content[rel_path] = (
                                    self._truncate_content_for_context(content)
                                )
                                self.logger.debug(f"Added file: {rel_path}")
                    except Exception as e:
                        self.logger.warning(
                            f"Could not read file {file_path}: {e}")

                elapsed_time = time.time() - start_time
                self.logger.info(
                    f"File collection complete in {elapsed_time:.2f}s. Total files: {len(files_content)}"
                )
                return files_content

            # Enhanced scoring system for file relevance
            self.logger.debug("Starting file relevance scoring...")
            scored_files = self._score_files(all_files, query)
            self.logger.info(f"Scored {len(scored_files)} relevant files")

            # Get top relevant files with parallel content loading
            top_files = sorted(scored_files, key=lambda x: x[2],
                               reverse=True)[:10]
            self.logger.debug(
                f"Selected top {len(top_files)} files for processing")

            # Load contents in parallel
            with ThreadPoolExecutor(max_workers=4) as executor:
                self.logger.debug("Starting parallel content loading...")
                results = executor.map(self._load_file_content, top_files)
                for result in results:
                    if result:
                        rel_path, content = result
                        # Truncate content for context
                        files_content[
                            rel_path] = self._truncate_content_for_context(
                                content)
                        self.logger.debug(f"Loaded content for: {rel_path}")

            elapsed_time = time.time() - start_time
            self.logger.info(
                f"File processing complete in {elapsed_time:.2f}s. Files loaded: {len(files_content)}"
            )
            return files_content

        except Exception as e:
            self.logger.error(f"Error processing workspace files: {str(e)}",
                              exc_info=True)
            return {}

    def _parallel_scan(self, workspace_dir: str) -> List[Tuple[str, str]]:
        """Helper method for parallel directory scanning"""

        def process_directory(dir_path: str) -> List[Tuple[str, str]]:
            files = []
            try:
                with os.scandir(dir_path) as it:
                    for entry in it:
                        if (entry.is_file() and not entry.name.startswith(".")
                                and not entry.name.endswith(
                                    tuple(self.SKIP_EXTENSIONS))):
                            rel_path = os.path.relpath(entry.path,
                                                       workspace_dir)
                            if not self._should_ignore(rel_path):
                                files.append((entry.path, rel_path))
                        elif (entry.is_dir() and not entry.name.startswith(".")
                              and entry.name not in self.SKIP_FOLDERS):
                            files.extend(process_directory(entry.path))
            except OSError as e:
                self.logger.error(
                    f"Error scanning directory {dir_path}: {str(e)}")
            return files

        subdirs = []
        files = []
        try:
            with os.scandir(workspace_dir) as it:
                for entry in it:
                    if (entry.is_dir() and not entry.name.startswith(".")
                            and entry.name not in self.SKIP_FOLDERS):
                        subdirs.append(entry.path)
                    elif (entry.is_file() and not entry.name.startswith(".")
                          and not entry.name.endswith(
                              tuple(self.SKIP_EXTENSIONS))):
                        rel_path = os.path.relpath(entry.path, workspace_dir)
                        if not self._should_ignore(rel_path):
                            files.append((entry.path, rel_path))
        except OSError as e:
            self.logger.error(f"Error scanning root directory: {str(e)}")

        if subdirs:
            with ThreadPoolExecutor(max_workers=4) as executor:
                subdir_files = list(executor.map(process_directory, subdirs))
                for subdir_file_list in subdir_files:
                    files.extend(subdir_file_list)

        return files

    def _score_files(self, files: List[Tuple[str, str]],
                     query: str) -> List[Tuple[str, str, float]]:
        """Score files based on relevance to query"""
        scored_files = []
        for file_path, rel_path in files:
            score = 0
            try:
                # Check filename relevance
                if any(term.lower() in rel_path.lower()
                       for term in query.lower().split()):
                    score += 5
                    self.logger.debug(
                        f"File {rel_path} matched query in name (+5)")

                # Quick content scan for relevance
                try:
                    with open(file_path, "rb") as f:
                        with mmap.mmap(f.fileno(), 0,
                                       access=mmap.ACCESS_READ) as mm:
                            preview = mm.read(4096).decode("utf-8",
                                                           errors="ignore")
                            if any(term.lower() in preview.lower()
                                   for term in query.lower().split()):
                                score += 3
                                self.logger.debug(
                                    f"File {rel_path} matched query in content (+3)"
                                )
                except (ValueError, OSError):
                    with open(file_path,
                              "r",
                              encoding="utf-8",
                              errors="ignore") as f:
                        preview = f.read(4096)
                        if any(term.lower() in preview.lower()
                               for term in query.lower().split()):
                            score += 3
                            self.logger.debug(
                                f"File {rel_path} matched query in content (+3)"
                            )

                # Consider file location and type
                if os.path.dirname(rel_path) == "":
                    score += 2
                    self.logger.debug(
                        f"File {rel_path} is in root directory (+2)")
                if rel_path.endswith(
                    (".py", ".js", ".html", ".css", ".json", ".yml", ".yaml")):
                    score += 1
                    self.logger.debug(
                        f"File {rel_path} is a primary file type (+1)")

                # Consider indexed symbols if available
                if file_path in self._file_index:
                    index = self._file_index[file_path]
                    for symbol_list in index["symbols"].values():
                        if any(term.lower() in symbol[1].lower()
                               for term in query.lower().split()
                               for symbol in symbol_list):
                            score += 2
                            self.logger.debug(
                                f"File {rel_path} matched query in symbols (+2)"
                            )

                if score > 0:
                    scored_files.append((file_path, rel_path, score))
                    self.logger.debug(f"File {rel_path} total score: {score}")
            except Exception as e:
                self.logger.warning(f"Could not analyze file {file_path}: {e}")

        return scored_files

    def _load_file_content(
            self, file_tuple: Tuple[str, str,
                                    float]) -> Optional[Tuple[str, str]]:
        """Load file content with proper error handling"""
        file_path, rel_path, _ = file_tuple
        try:
            content = self._get_file_content(file_path)
            if content:
                self.logger.debug(
                    f"Successfully loaded content for {rel_path}")
                return rel_path, content
        except Exception as e:
            self.logger.warning(f"Could not read file {file_path}: {e}")
        return None

    def _load_gitignore(self):
        """Load .gitignore patterns if the file exists"""
        gitignore_path = os.path.join(self.workspace_root, ".gitignore")
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, "r") as f:
                    patterns = []
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # Convert glob patterns to regex patterns
                            pattern = (line.replace(".", r"\.").replace(
                                "*", ".*").replace("?", "."))
                            if not line.startswith("/"):
                                pattern = f".*{pattern}"
                            if not line.endswith("/"):
                                pattern = f"{pattern}($|/.*)"
                            patterns.append(pattern)
                    self._gitignore_patterns = patterns
            except Exception as e:
                print(f"Warning: Could not read .gitignore file: {e}")

    def _should_ignore(self, path: str) -> bool:
        """Check if a path should be ignored based on gitignore patterns"""
        if not self._gitignore_patterns:
            return False

        normalized_path = path.replace("\\", "/")
        return any(
            re.match(pattern, normalized_path)
            for pattern in self._gitignore_patterns)

    def _is_cache_valid(
            self, path: str, cache_entry: Tuple[Union[str, List[dict]],
                                                float]) -> bool:
        """Check if cached content is still valid"""
        try:
            current_mtime = os.path.getmtime(path)
            return current_mtime == cache_entry[1]
        except OSError:
            return False

    def get_directory_structure(self,
                                dir_path: str,
                                depth: int = 1) -> List[dict]:
        """Get directory structure with lazy loading support"""
        try:
            # Use the provided path directly if it's absolute, otherwise join
            # with workspace root
            abs_path = (dir_path if os.path.isabs(dir_path) else os.path.join(
                self.workspace_root, dir_path))
            result = []

            for entry in os.scandir(abs_path):
                # Skip hidden files, .git directory, and other ignored
                # directories
                if entry.name.startswith(".") or (entry.is_dir() and entry.name
                                                  in self.SKIP_FOLDERS):
                    continue

                # Get path relative to current directory instead of workspace
                # root
                rel_path = os.path.relpath(entry.path, abs_path)

                # Skip if path matches gitignore patterns
                if self._should_ignore(rel_path):
                    continue

                if entry.is_file() and not any(
                        rel_path.endswith(ext)
                        for ext in self.SKIP_EXTENSIONS):
                    result.append({
                        "type": "file",
                        "path": rel_path.replace("\\", "/"),
                        "size": entry.stat().st_size,
                    })
                elif entry.is_dir() and depth > 0:
                    children = (self.get_directory_structure(
                        entry.path, depth - 1) if depth > 1 else [])
                    result.append({
                        "type":
                        "directory",
                        "path":
                        rel_path.replace("\\", "/"),
                        "has_children":
                        bool(children)
                        or any(True for _ in os.scandir(entry.path)),
                        "children":
                        children,
                    })

            return sorted(result,
                          key=lambda x:
                          (x["type"] != "directory", x["path"].lower()))

        except OSError:
            return []

    def get_workspace_structure(self, workspace_dir: str) -> List[dict]:
        """Get workspace structure with lazy loading for large directories"""
        try:
            # Check if we have a valid cached structure
            if workspace_dir in self._structure_cache:
                structure, mtime = self._structure_cache[workspace_dir]
                if os.path.getmtime(workspace_dir) == mtime:
                    return structure

            # Count total files to determine if we should use lazy loading
            total_files = 0
            print(f"\nCounting files in {workspace_dir}:")
            for root, dirs, files in os.walk(workspace_dir):
                # Skip .git and other ignored directories
                original_dirs = set(dirs)
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".") and d not in self.SKIP_FOLDERS
                ]
                if len(original_dirs) != len(dirs):
                    print(
                        f"Skipped directories in {root}: {original_dirs - set(dirs)}"
                    )

                # Filter files based on gitignore and skip patterns
                for file in files:
                    if not file.startswith(".") and not file.endswith(
                            tuple(self.SKIP_EXTENSIONS)):
                        rel_path = os.path.relpath(os.path.join(root, file),
                                                   workspace_dir)
                        if not self._should_ignore(rel_path):
                            total_files += 1
                            print(f"Counting file: {rel_path}")
                        else:
                            print(f"Ignoring file (gitignore): {rel_path}")
                    else:
                        print(f"Ignoring file (hidden/extension): {file}")

            print(f"\nTotal files counted: {total_files}")

            if total_files > self.LAZY_LOAD_THRESHOLD:
                # Use lazy loading - only get top-level structure
                structure = self.get_directory_structure(workspace_dir,
                                                         depth=1)
            else:
                # Get full structure for smaller workspaces
                structure = self.get_directory_structure(workspace_dir,
                                                         depth=float("inf"))

            self._structure_cache[workspace_dir] = (
                structure,
                os.path.getmtime(workspace_dir),
            )
            return structure

        except OSError:
            return []

    def expand_directory(self,
                         dir_path: str,
                         workspace_dir: str,
                         page_size: int = 100,
                         page: int = 1) -> dict:
        """Expand a directory node for lazy loading with pagination support

        Args:
            dir_path: Directory path to expand
            workspace_dir: The workspace directory containing the files
            page_size: Number of items per page
            page: Page number (1-based)

        Returns:
            Dictionary containing:
            - items: List of files and directories in the current page
            - total_items: Total number of items
            - has_more: Whether there are more items
        """
        try:
            # Ensure we have absolute paths
            if os.path.isabs(dir_path):
                abs_path = dir_path
                # Verify the path is within workspace directory
                if not os.path.abspath(abs_path).startswith(
                        os.path.abspath(workspace_dir)):
                    raise ValueError("Path is outside workspace directory")
            else:
                abs_path = os.path.join(workspace_dir, dir_path)

            print(f"Expanding directory: {abs_path}")  # Debug log

            if not os.path.exists(abs_path):
                print(f"Directory not found: {abs_path}")  # Debug log
                raise ValueError(f"Directory not found: {dir_path}")

            if not os.path.isdir(abs_path):
                print(f"Not a directory: {abs_path}")  # Debug log
                raise ValueError(f"Not a directory: {dir_path}")

            # Get all entries first
            entries = []
            start_idx = (page - 1) * page_size

            try:
                with os.scandir(abs_path) as it:
                    for entry in it:
                        try:
                            # Skip hidden files and ignored directories
                            if entry.name.startswith(".") or (
                                    entry.is_dir()
                                    and entry.name in self.SKIP_FOLDERS):
                                print(f"Skipping {entry.name} (hidden/ignored)"
                                      )  # Debug log
                                continue

                            # Get path relative to current directory
                            entry_rel_path = os.path.relpath(
                                entry.path, abs_path)

                            # Skip if path matches gitignore patterns
                            if self._should_ignore(entry_rel_path):
                                print(f"Skipping {entry_rel_path} (gitignore)"
                                      )  # Debug log
                                continue

                            if entry.is_file() and not any(
                                    entry_rel_path.endswith(ext)
                                    for ext in self.SKIP_EXTENSIONS):
                                # Debug log
                                print(f"Adding file: {entry_rel_path}")
                                entries.append({
                                    "type":
                                    "file",
                                    "path":
                                    entry_rel_path.replace("\\", "/"),
                                    "size":
                                    entry.stat().st_size,
                                })
                            elif entry.is_dir():
                                # For directories, check if they have children
                                # without loading them all
                                has_children = False
                                try:
                                    with os.scandir(entry.path) as dir_it:
                                        for child in dir_it:
                                            if not child.name.startswith(
                                                    ".") and not (
                                                        child.is_dir()
                                                        and child.name
                                                        in self.SKIP_FOLDERS):
                                                has_children = True
                                                break
                                except OSError as e:
                                    print(
                                        f"Error checking directory contents: {e}"
                                    )  # Debug log
                                    pass

                                print(
                                    f"Adding directory: {entry_rel_path} (has_children={has_children})"
                                )  # Debug log
                                entries.append({
                                    "type":
                                    "directory",
                                    "path":
                                    entry_rel_path.replace("\\", "/"),
                                    "has_children":
                                    has_children,
                                })
                        except OSError as e:
                            print(f"Error processing entry {entry.name}: {e}"
                                  )  # Debug log
                            continue
            except OSError as e:
                print(f"Error scanning directory {abs_path}: {e}")  # Debug log
                raise

            # Sort entries (directories first, then alphabetically)
            entries.sort(
                key=lambda x: (x["type"] != "directory", x["path"].lower()))

            # Get total count and slice for current page
            total_items = len(entries)
            page_entries = entries[start_idx:start_idx + page_size]

            print(
                f"Directory expansion results: {len(page_entries)} items (total: {total_items})"
            )  # Debug log

            return {
                "items": page_entries,
                "total_items": total_items,
                "has_more": (start_idx + page_size) < total_items,
            }

        except Exception as e:
            print(f"Error in expand_directory: {str(e)}")  # Debug log
            raise

    def clear_cache(self, file_path: Optional[str] = None):
        """Clear cache entries"""
        if file_path:
            self._content_cache.pop(file_path, None)
            self._chunk_cache.pop(file_path, None)
        else:
            self._content_cache.clear()
            self._structure_cache.clear()
            self._chunk_cache.clear()

    def get_workspace_context(self, workspace_dir: str) -> str:
        """Get a description of the workspace context"""
        self.logger.info(f"Getting workspace context for: {workspace_dir}")
        start_time = time.time()

        try:
            # Get workspace structure with progress logging
            self.logger.debug("Fetching workspace structure...")
            structure = self.get_workspace_structure(workspace_dir)
            self.logger.debug(
                f"Found {len(structure)} top-level items in structure")

            # Get relevant files with size limits and logging
            self.logger.debug("Fetching workspace files...")
            files_content = {}
            total_size = 0

            # Only process files under size threshold
            for root, _, files in os.walk(workspace_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        if os.path.getsize(
                                file_path) < self.LARGE_FILE_THRESHOLD:
                            rel_path = os.path.relpath(file_path,
                                                       workspace_dir)
                            if not self._should_ignore(rel_path):
                                content = self._get_file_content(file_path)
                                if content:
                                    files_content[rel_path] = content
                                    total_size += len(content.encode("utf-8"))
                                    self.logger.debug(
                                        f"Added {rel_path} to context (size: {len(content)} chars)"
                                    )
                    except OSError as e:
                        self.logger.warning(
                            f"Error processing file {file_path}: {e}")

            # Build context string with structure
            context = "Workspace Structure:\n"
            for item in structure:
                prefix = "📁 " if item["type"] == "directory" else " "
                context += f"{prefix}{item['path']}\n"

            # Add dependencies if files were processed
            if files_content:
                context += "\nFile Relationships and Dependencies:\n"
                dependencies = self._analyze_dependencies(files_content)
                for file, deps in dependencies.items():
                    if deps:
                        context += f"{file} depends on: {', '.join(deps)}\n"

            elapsed_time = time.time() - start_time
            self.logger.info(
                f"Context generation complete in {elapsed_time:.2f}s")
            self.logger.info(
                f"Context size: {len(context)} chars, Files processed: {len(files_content)}"
            )

            return context

        except Exception as e:
            self.logger.error(f"Error generating workspace context: {str(e)}",
                              exc_info=True)
            return f"Error generating context: {str(e)}"

    def process_operations(self, operations: List[dict],
                           workspace_dir: str) -> List[dict]:
        """Process and validate operations, adding diffs for changes

        Args:
            operations: List of operations to process
            workspace_dir: The workspace directory path
        """
        processed = []
        for operation in operations:
            try:
                # First validate the operation content before cleaning paths
                if operation["type"] == "edit_file":
                    changes = operation.get("changes", [])
                    if not changes:
                        raise ValueError(
                            f"No changes specified for edit operation on {operation.get('path', 'unknown file')}"
                        )

                    for i, change in enumerate(changes):
                        if not isinstance(change, dict):
                            raise ValueError(
                                f"Invalid change format at index {i} in {operation.get('path', 'unknown file')}"
                            )

                        if "old" not in change or "new" not in change:
                            raise ValueError(
                                f"Change at index {i} missing 'old' or 'new' field in {operation.get('path', 'unknown file')}"
                            )

                        # For edit operations, at least one of old or new must
                        # be non-empty
                        if not change["old"].strip(
                        ) and not change["new"].strip():
                            raise ValueError(
                                f"Change at index {i} has empty 'old' and 'new' content in {operation.get('path', 'unknown file')}"
                            )

                elif operation["type"] == "create_file":
                    # For create operations, only validate if the file doesn't
                    # exist
                    file_path = os.path.join(workspace_dir, operation["path"])
                    if (not os.path.exists(file_path)
                            and not operation.get("content", "").strip()):
                        raise ValueError(
                            f"Empty or incomplete content for new file {operation.get('path', 'unknown file')}"
                        )

                # After validation, clean the paths for processing
                if "path" in operation:
                    operation["path"] = operation["path"].split("?")[0].split(
                        "#")[0]
                if "new_path" in operation:
                    operation["new_path"] = (
                        operation["new_path"].split("?")[0].split("#")[0])

                if operation["type"] == "edit_file":
                    # Get current content if file exists
                    file_path = os.path.join(workspace_dir, operation["path"])
                    current_content = ""
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                current_content = f.read()
                        except UnicodeDecodeError:
                            try:
                                with open(file_path, "r",
                                          encoding="latin-1") as f:
                                    current_content = f.read()
                            except Exception:
                                pass

                    # Generate unified diff
                    from difflib import unified_diff

                    changes = operation.get("changes", [])
                    new_content = current_content
                    for change in changes:
                        if "old" in change and "new" in change:
                            # Ensure we're not adding extra newlines during
                            # replacement
                            old_text = change["old"].rstrip("\n")
                            new_text = change["new"].rstrip("\n")
                            new_content = new_content.replace(
                                old_text, new_text)

                    # Ensure both contents end with exactly one newline
                    current_content = current_content.rstrip("\n") + "\n"
                    new_content = new_content.rstrip("\n") + "\n"

                    # Generate diff with proper header formatting
                    diff = [
                        f'--- a/{operation["path"]}\n',
                        f'+++ b/{operation["path"]}\n',
                    ]

                    # Get the diff content
                    diff_content = unified_diff(
                        current_content.splitlines(keepends=True),
                        new_content.splitlines(keepends=True),
                        fromfile="",  # Empty since we handle headers separately
                        tofile="",
                        lineterm=
                        "\n",  # Add newline to each line including hunk header
                    )
                    # Skip the first two lines (headers) from unified_diff
                    next(diff_content)  # Skip first header
                    next(diff_content)  # Skip second header

                    # Add the rest of the diff content, filtering out empty
                    # added/removed lines
                    filtered_content = [
                        line for line in diff_content
                        if not (line.startswith("+") or line.startswith("-"))
                        or line.strip() not in ("+", "-")
                    ]
                    diff.extend(filtered_content)
                    operation["diff"] = "".join(diff)

                    # Run linter on Python files
                    if operation["path"].endswith(".py"):
                        import subprocess
                        import tempfile

                        # Create temporary file with new content
                        with tempfile.NamedTemporaryFile(mode="w",
                                                         suffix=".py",
                                                         delete=False) as tmp:
                            tmp.write(new_content)
                            tmp_path = tmp.name

                        try:
                            # Run pylama
                            result = subprocess.run(["pylama", tmp_path],
                                                    capture_output=True,
                                                    text=True)
                            # Combine stdout and stderr for complete output
                            operation["lint_output"] = result.stdout
                            if result.stderr:
                                operation["lint_output"] += "\n" + \
                                    result.stderr
                            operation["lint_passed"] = result.returncode == 0
                        except Exception as e:
                            print(f"Linting error: {str(e)}")
                            operation[
                                "lint_output"] = f"Linting failed: {str(e)}"
                            operation["lint_passed"] = False
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except Exception as e:
                                print(f"Failed to cleanup temp file: {str(e)}")
                    else:
                        # Non-Python files don't need linting
                        operation["lint_passed"] = True
                        operation["lint_output"] = ""

                elif operation["type"] == "create_file":
                    # For new files, show the entire content as added
                    diff = [
                        "--- /dev/null\n",
                        f'+++ b/{operation["path"]}\n',
                        "@@ -0,0 +1,{} @@\n".format(
                            operation["content"].count("\n") + 1),
                    ]
                    diff.extend(f"+{line}\n"
                                for line in operation["content"].splitlines())
                    operation["diff"] = "".join(diff)

                    # Run linter on new Python files
                    if operation["path"].endswith(".py"):
                        import subprocess
                        import tempfile

                        # Create temporary file with content
                        with tempfile.NamedTemporaryFile(mode="w",
                                                         suffix=".py",
                                                         delete=False) as tmp:
                            tmp.write(operation["content"])
                            tmp_path = tmp.name

                        try:
                            # Run pylama
                            result = subprocess.run(["pylama", tmp_path],
                                                    capture_output=True,
                                                    text=True)
                            # Combine stdout and stderr for complete output
                            operation["lint_output"] = result.stdout
                            if result.stderr:
                                operation["lint_output"] += "\n" + \
                                    result.stderr
                            operation["lint_passed"] = result.returncode == 0
                        except Exception as e:
                            print(f"Linting error: {str(e)}")
                            operation[
                                "lint_output"] = f"Linting failed: {str(e)}"
                            operation["lint_passed"] = False
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except Exception as e:
                                print(f"Failed to cleanup temp file: {str(e)}")
                    else:
                        # Non-Python files don't need linting
                        operation["lint_passed"] = True
                        operation["lint_output"] = ""

                elif operation["type"] == "remove_file":
                    # For file removal, show the entire content as removed
                    file_path = os.path.join(workspace_dir, operation["path"])
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                content = f.read()
                        except UnicodeDecodeError:
                            with open(file_path, "r", encoding="latin-1") as f:
                                content = f.read()

                        diff = [
                            f'--- a/{operation["path"]}\n',
                            "+++ /dev/null\n",
                            "@@ -1,{} +0,0 @@\n".format(
                                content.count("\n") + 1),
                        ]
                        diff.extend(f"-{line}\n"
                                    for line in content.splitlines())
                        operation["diff"] = "".join(diff)
                    else:
                        operation["diff"] = ""

                    # No linting needed for file removal
                    operation["lint_passed"] = True
                    operation["lint_output"] = ""

                processed.append(operation)

            except Exception as e:
                print(f"Error processing operation: {str(e)}")
                operation["error"] = str(e)
                operation["lint_passed"] = False
                operation["lint_output"] = str(e)
                processed.append(operation)

        return processed

    def search_codebase(self,
                        query: str,
                        top_k: int = 10) -> List[Tuple[str, float, str]]:
        """Search the codebase using BM25"""
        self.logger.info(f"Searching codebase for: {query}")
        return self.search_index.search(query, top_k)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in a text.
        This is a rough estimate - actual token count may vary by model."""
        # Average English word length is 4.7 characters
        # Average token is about 4 characters
        # So we estimate 1 token per 4 characters
        return len(text) // 4

    def _truncate_content_for_context(self,
                                      content: str,
                                      max_tokens: int = 60000) -> str:
        """Truncate file content while preserving important parts and staying within token limit.

        Args:
            content: The file content to truncate
            max_tokens: Maximum number of tokens to allow

        Returns:
            Truncated content with summary
        """
        # First check if we're already under the limit
        if self._estimate_tokens(content) <= max_tokens:
            return content

        lines = content.splitlines()

        # Start with smaller chunks and increase if needed
        keep_start = 50
        keep_end = 50
        remaining_lines = 100

        while True:
            # Get the first section
            truncated = lines[:keep_start]

            # Get evenly spaced lines from middle section
            middle_start = keep_start
            middle_end = len(lines) - keep_end
            middle_lines = lines[middle_start:middle_end]

            if middle_lines:
                # Calculate step size to get remaining_lines number of lines
                step = len(middle_lines) // remaining_lines
                if step > 1:
                    truncated.append(f"\n... truncated {step} lines ...\n")
                    truncated.extend(middle_lines[::step][:remaining_lines])
                    truncated.append(f"\n... truncated {step} lines ...\n")
                else:
                    truncated.extend(middle_lines[:remaining_lines])

            # Add the last section
            truncated.extend(lines[-keep_end:])

            result = "\n".join(truncated)
            if self._estimate_tokens(result) <= max_tokens:
                return result

            # If still too large, reduce the number of lines we keep
            if keep_start > 10:
                keep_start -= 10
                keep_end -= 10
                remaining_lines = max(20, remaining_lines - 20)
            else:
                # If we can't reduce further, return a minimal version
                return "\n".join(
                    lines[:10] +
                    [f"\n... truncated {len(lines) - 20} lines ...\n"] +
                    lines[-10:])

    def is_large_file(self, file_path: str) -> bool:
        """Check if a file is considered large based on LARGE_FILE_THRESHOLD"""
        try:
            return os.path.getsize(file_path) > self.LARGE_FILE_THRESHOLD
        except OSError:
            return False
