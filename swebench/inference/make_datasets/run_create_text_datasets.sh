#!/bin/bash

set -x

file_source=oracle
output_dir=outputs/text_datasets_${file_source}
prompt_style=style-3-fixed

for repo_name in langchain openai-python transformers pydantic-ai
do

if [ $file_source == "bm25" ]; then
retireval_file="--retrieval_file=outputs/retrieval_results/outputs__tasks__${repo_name}-task-instances_cleaned.jsonl__${prompt_style}__fs-oracle/file_name_and_contents.retrieval.jsonl"
else
retireval_file=""
fi

python swebench/inference/make_datasets/create_text_dataset.py --prompt_style=${prompt_style} --dataset_name_or_path=outputs/tasks/${repo_name}-task-instances_cleaned.jsonl --split=train --output_dir=$output_dir --validation_ratio=0 --file_source=$file_source --copy_repo_from_host_path=repos/$repo_name $retireval_file
done