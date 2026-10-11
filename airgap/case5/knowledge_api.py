#!/usr/bin/env python3

import json
import math
import os
import re
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

DOCS_DIR = "/opt/knowledge/docs"
HOST = "0.0.0.0"
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
            "content": content
        })

    return documents


def tfidf_search(query, documents):
    if not documents:
        return []

    query_tokens = tokenize(query)
    query_tf = Counter(query_tokens)

    document_tokens = [
        tokenize(doc["content"])
        for doc in documents
    ]

    document_tf = [
        Counter(tokens)
        for tokens in document_tokens
    ]

    all_terms = set(query_tokens)

    for tokens in document_tokens:
        all_terms.update(tokens)

    document_count = len(documents)

    df = {}

    for term in all_terms:
        df[term] = sum(
            1 for tokens in document_tokens
            if term in tokens
        )

    idf = {
        term: math.log((document_count + 1) / (df[term] + 1)) + 1
        for term in all_terms
    }

    query_vector = {
        term: query_tf[term] * idf[term]
        for term in query_tf
    }

    query_norm = math.sqrt(
        sum(value * value for value in query_vector.values())
    )

    results = []

    for doc, tf in zip(documents, document_tf):
        doc_vector = {
            term: tf[term] * idf[term]
            for term in tf
            if term in idf
        }

        doc_norm = math.sqrt(
            sum(value * value for value in doc_vector.values())
        )

        dot_product = sum(
            query_vector.get(term, 0) * doc_vector.get(term, 0)
            for term in query_vector
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

    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return results


class KnowledgeHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path != "/search":
            self.send_error(404)
            return

        params = parse_qs(parsed.query)
        query = params.get("q", [""])[0].strip()

        if not query:
            self.send_error(400, "Missing query")
            return

        documents = load_documents()

        # Vulnerable state:
        # 모든 Knowledge가 사용자 권한과 관계없이 Retrieval 후보가 된다.
        allowed_documents = documents

        results = tfidf_search(query, allowed_documents)

        result = (
            results[0]
            if results and results[0]["score"] > 0
            else None
        )

        ranking = [
            {
                "document": item["document"],
                "score": item["score"]
            }
            for item in results
        ]

        body = json.dumps({
            "query": query,
            "ranking": ranking,
            "result": result
        }, ensure_ascii=False, indent=2).encode("utf-8")

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header(
            "Content-Length",
            str(len(body))
        )
        self.end_headers()

        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), KnowledgeHandler)

    print(
        f"Knowledge API listening on "
        f"http://{HOST}:{PORT}"
    )

    server.serve_forever()
