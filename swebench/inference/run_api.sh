
model=gpt-4-1106-preview
#gpt-4o

#gpt-4-1106-preview

retrieval=bm25

for repo_name in transformers pydantic-ai langchain openai-python
do
        python swebench/inference/run_api.py --dataset_name_or_path=outputs/text_datasets_${retrieval}/outputs__tasks__${repo_name}-task-instances_cleaned.jsonl__style-3__fs-${retrieval} --model_name_or_path=${model} --output_dir=outputs/inference
done


