set -x

dataset_dir="outputs/tasks"
max_instances=20
run_id=100
model=gpt-4o
retrieval=oracle
prompt_style=style-3-fixed

for repo_name in langchain openai-python pydantic-ai transformers
do
    dataset_name=${repo_name}-task-instances_cleaned
    echo "Running $dataset_name"
    dataset_path="$dataset_dir/${dataset_name}.jsonl"
    ids=$(python swebench/collect/get_instance_id.py --task=$dataset_path --max_instances=$max_instances)
    
    python -m swebench.harness.run_evaluation --dataset_name=$dataset_path --instance_ids $ids --predictions_path=outputs/inference/${model}__outputs__tasks__${repo_name}-task-instances_cleaned.jsonl__${prompt_style}__fs-${retrieval}__train.jsonl --report_dir=outputs/reports/$dataset_name --run_id=$run_id --namespace="" --cache_level="base" --force_rebuild=true

    run_id=$((run_id+1))
done

