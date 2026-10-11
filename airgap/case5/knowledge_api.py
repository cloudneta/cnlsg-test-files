#!/usr/bin/env python3

import json
import math
import os
import re
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

DOCS_DIR = "/opt/knowledge/docs"
PORT = 8080


def tokenize(text):
    return re.findall(r"[A-Za-z0-9가-힣_-]+", text.lower())


def load_documents():
    documents = []

    for filename in sorted(os.listdir(DOCS_DIR)):
        if not filename.endswith(".md"):
            continue

        path = os.path.join(DOCS_DIR, filename)

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        documents.append({
            "name": filename,
            "content": content,
            "tokens": tokenize(content)
        })

    return documents


def tfidf_search(query, documents):
    query_tokens = tokenize(query)

    if not query_tokens or not documents:
        return []

    document_count = len(documents)

    document_frequency = Counter()

    for doc in documents:
        for token in set(doc["tokens"]):
            document_frequency[token] += 1

    def idf(token):
        return math.log((document_count + 1) /
                        (document_frequency.get(token, 0) + 1)) + 1

    query_tf = Counter(query_tokens)
    query_vector = {
        token: count * idf(token)
        for token, count in query_tf.items()
    }

    results = []

    for doc in documents:
        doc_tf = Counter(doc["tokens"])

        doc_vector = {
            token: count * idf(token)
            for token, count in doc_tf.items()
        }

        common_tokens = set(query_vector) & set(doc_vector)

        dot_product = sum(
            query_vector[token] * doc_vector[token]
            for token in common_tokens
        )

        query_norm = math.sqrt(
            sum(value * value for value in query_vector.values())
        )

        doc_norm = math.sqrt(
            sum(value * value for value in doc_vector.values())
        )

        if query_norm == 0 or doc_norm == 0:
            score = 0.0
        else:
            score = dot_product / (query_norm * doc_norm)

        results.append({
            "document": doc["name"],
            "score": round(score, 4),
            "content": doc["content"]
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    return results


class KnowledgeHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path != "/search":
            self.send_error(404)
            return

        params = parse_qs(parsed.query)
        query = params.get("q", [""])[0]

        documents = load_documents()
        results = tfidf_search(query, documents)

        result = results[0] if results and results[0]["score"] > 0 else None

        body = json.dumps({
            "query": query,
            "result": result
        }, ensure_ascii=False, indent=2).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    print(f"Knowledge API listening on 0.0.0.0:{PORT}")
    HTTPServer(("0.0.0.0", PORT), KnowledgeHandler).serve_forever()
