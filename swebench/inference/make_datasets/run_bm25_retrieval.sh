#!/bin/bash

set -x

output_dir=outputs/retrieval_results


for repo_name in langchain openai-python transformers pydantic-ai
do
 python swebench/inference/make_datasets/bm25_retrieval.py --dataset_name_or_path=outputs/text_datasets_oracle/outputs__tasks__${repo_name}-task-instances_cleaned.jsonl__style-3__fs-oracle --copy_repo_from_host_path=repos/${repo_name}/ --output_dir=$output_dir
done