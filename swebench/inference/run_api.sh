
model=gpt-4o
#Qwen2.5-Coder-7B-Instruct
#gpt-4-1106-preview
prompt_style=style-3-fixed
retrieval=oracle

for repo_name in transformers pydantic-ai langchain openai-python
do
        python swebench/inference/run_api.py --dataset_name_or_path=outputs/text_datasets_${retrieval}/outputs__tasks__${repo_name}-task-instances_cleaned.jsonl__${prompt_style}__fs-${retrieval} --model_name_or_path=${model} --output_dir=outputs/inference
done


