import json
import logging
import os
import traceback
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unidiff
from tqdm.auto import tqdm
from datetime import datetime

from swebench.inference.make_datasets.tokenize_dataset import TOKENIZER_FUNCS
from swebench.inference.make_datasets.utils import (
    AutoContextManager,
    ingest_directory_contents,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


PATCH_EXAMPLE = """--- a/file.py
+++ b/file.py
@@ -1,27 +1,35 @@
 def euclidean(a, b):
-    while b:
-        a, b = b, a % b
-    return a
+    if b == 0:
+        return a
+    return euclidean(b, a % b)
 
 
 def bresenham(x0, y0, x1, y1):
     points = []
     dx = abs(x1 - x0)
     dy = abs(y1 - y0)
-    sx = 1 if x0 < x1 else -1
-    sy = 1 if y0 < y1 else -1
-    err = dx - dy
+    x, y = x0, y0
+    sx = -1 if x0 > x1 else 1
+    sy = -1 if y0 > y1 else 1
 
-    while True:
-        points.append((x0, y0))
-        if x0 == x1 and y0 == y1:
-            break
-        e2 = 2 * err
-        if e2 > -dy:
+    if dx > dy:
+        err = dx / 2.0
+        while x != x1:
+            points.append((x, y))
             err -= dy
-            x0 += sx
-        if e2 < dx:
-            err += dx
-            y0 += sy
+            if err < 0:
+                y += sy
+                err += dx
+            x += sx
+    else:
+        err = dy / 2.0
+        while y != y1:
+            points.append((x, y))
+            err -= dx
+            if err < 0:
+                x += sx
+                err += dy
+            y += sy
 
+    points.append((x, y))
     return points"""


FULL_GENERATION_EXAMPLE = """[start of /src/this_file.py]
import os

def euclidean(a, b):
    if b == 0:
        return a
    return euclidean(b, a % b)
[end of /src/this_file.py]
[start of /src/another_file.py]
def bresenham(x0, y0, x1, y1):
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    x, y = x0, y0
    sx = -1 if x0 > x1 else 1
    sy = -1 if y0 > y1 else 1
    if dx > dy:
        err = dx / 2.0
        while x != x1:
            points.append((x, y))
            err -= dy
            if err < 0:
                y += sy
                err += dx
            x += sx
    else:
        err = dy / 2.0
        while y != y1:
            points.append((x
            err -= dx
            if err < 0:
                x += sx
                err += dy
            y += sy
    points.append((x, y))
    return points
[end of /src/another_file.py]"""


def add_lines_list(content):
    content_with_lines = list()
    for ix, line in enumerate(content.split("\n"), start=1):
        content_with_lines.append(f"{ix} {line}")
    return content_with_lines


def add_lines(content):
    return "\n".join(add_lines_list(content))


def make_code_text(files_dict, add_line_numbers=True):
    all_text = ""
    for filename, contents in sorted(files_dict.items()):
        all_text += f"[start of {filename}]\n"
        if add_line_numbers:
            all_text += add_lines(contents)
        else:
            all_text += contents
        all_text += f"\n[end of {filename}]\n"
    return all_text.strip("\n")


def make_code_text_edits_only(files_dict, patch, add_line_numbers=True):
    files = dict()
    patch = unidiff.PatchSet(patch)
    for patched_file in patch:
        source_file = patched_file.source_file.split("a/", 1)[-1]
        files[source_file] = list()
        for hunk in patched_file:
            start = hunk.source_start - 15
            end = start + hunk.source_length + 15
            files[source_file].append((start, end))
    all_text = ""
    for filename, content in files_dict.items():
        all_text += f"[start of {filename}]\n"
        content_with_lines = add_lines_list(content)
        for start, end in files[filename]:
            if start > 0:
                all_text += "...\n"
            all_text += "\n".join(content_with_lines[start:end])
            all_text += "\n"
            if end < len(content_with_lines):
                all_text += "...\n"
        all_text = all_text.strip("\n")
        all_text += f"\n[end of {filename}]\n"
    return all_text.strip("\n")


def prompt_style_2(instance):
    premise = "You will be provided with a partial code base and an issue statement explaining a problem to resolve."
    readmes_text = make_code_text(instance["readmes"])
    code_text = make_code_text(instance["file_contents"])
    instructions = (
        "I need you to solve this issue by generating a single patch file that I can apply "
        + "directly to this repository using git apply. Please respond with a single patch "
        + "file in the following format."
    )
    problem_statement = instance["problem_statement"]
    final_text = [
        premise,
        "<issue>",
        problem_statement,
        "</issue>",
        "<code>",
        readmes_text,
        code_text,
        "</code>",
        instructions,
        "<patch>",
        PATCH_EXAMPLE,
        "</patch>",
    ]
    final_text = "\n".join(final_text)
    return final_text


def prompt_style_2_edits_only(instance):
    premise = "You will be provided with a partial code base and an issue statement explaining a problem to resolve."
    readmes_text = make_code_text(instance["readmes"])
    code_text = make_code_text_edits_only(instance["file_contents"], instance["patch"])
    instructions = (
        "I need you to solve this issue by generating a single patch file that I can apply "
        + "directly to this repository using git apply. Please respond with a single patch "
        + "file in the following format."
    )
    problem_statement = instance["problem_statement"]
    final_text = [
        premise,
        "<issue>",
        problem_statement,
        "</issue>",
        "<code>",
        readmes_text,
        code_text,
        "</code>",
        instructions,
        "<patch>",
        PATCH_EXAMPLE,
        "</patch>",
    ]
    final_text = "\n".join(final_text)
    return final_text


def prompt_style_3(instance):
    premise = "You will be provided with a partial code base and an issue statement explaining a problem to resolve."
    readmes_text = make_code_text(instance["readmes"])
    code_text = make_code_text(instance["file_contents"])
    example_explanation = (
        "Here is an example of a patch file. It consists of changes to the code base. "
        + "It specifies the file names, the line numbers of each change, and the removed and added lines. "
        + "A single patch file can contain changes to multiple files."
    )
    final_instruction = (
        "I need you to solve the provided issue by generating a single patch file that I can apply "
        + "directly to this repository using git apply. Please respond with a single patch "
        + "file in the format shown above."
    )
    problem_statement = instance["problem_statement"]
    final_text = [
        premise,
        "<issue>",
        problem_statement,
        "</issue>",
        "",
        "<code>",
        readmes_text,
        code_text,
        "</code>",
        "",
        example_explanation,
        "<patch>",
        PATCH_EXAMPLE,
        "</patch>",
        "",
        final_instruction,
        "Respond below:",
    ]
    final_text = "\n".join(final_text)
    return final_text


PATCH_INSTRUCTIONS = """
When generating patch files (diff files), follow these strict formatting rules:

1. Patch Structure:
   - Always start with the header lines:
     ```
     --- a/path/to/original/file
     +++ b/path/to/modified/file
     ```
   - Include the hunk header with line numbers:
     ```
     @@ -start_line,count +start_line,count @@
     ```

2. Content Formatting:
   - Each line must start with either:
     - ` ` (space) for unchanged lines
     - `-` for removed lines
     - `+` for added lines
   - Maintain consistent indentation with the original file
   - Preserve all whitespace and line endings
   - Include complete function calls and statements
   - Never truncate or omit closing brackets, parentheses, or quotes

3. Code Block Rules:
   - Always include complete code blocks
   - For multi-line changes, maintain proper indentation
   - Include all necessary imports and dependencies
   - Preserve the original file's coding style and conventions

4. Common Pitfalls to Avoid:
   - Never leave incomplete function calls or statements
   - Don't omit closing brackets or parentheses
   - Don't truncate lines in the middle of a statement
   - Don't mix tabs and spaces
   - Don't change indentation levels without proper context

5. Validation Checklist:
   - Verify the patch can be applied with `git apply`
   - Ensure all function calls are complete
   - Check that all brackets and parentheses are properly closed
   - Confirm indentation matches the original file
   - Validate that the patch maintains the file's structure

6. Example of Correct Formatting:
   ```diff
   --- a/file.py
   +++ b/file.py
   @@ -10,7 +10,7 @@
        def example_function():
            if condition:
                return True
   -        return False
   +        return True
   ```

7. Error Prevention:
   - Always include complete context around changes
   - Maintain proper line endings
   - Use consistent quote styles
   - Include all necessary imports
   - Preserve file encoding

8. Testing:
   - Verify the patch can be applied cleanly
   - Check for any syntax errors
   - Ensure the changes maintain code functionality
   - Validate against the original file's style guide

Remember: A well-formatted patch should be:
- Complete (no truncated lines)
- Consistent (matching original file style)
- Correct (syntactically valid)
- Clean (properly formatted)
- Contextual (includes necessary surrounding code)
"""

def prompt_style_3_fixed(instance):
    premise = "You will be provided with a partial code base and an issue statement explaining a problem to resolve. Your task is to change python source files. Be carefull generating patch files, double check python indentation and syntax."
    readmes_text = make_code_text(instance["readmes"])
    code_text = make_code_text(instance["file_contents"])
    example_explanation = (
        "Here is an example of a patch file. It consists of changes to the code base. "
        + "It specifies the file names, the line numbers of each change, and the removed and added lines. "
        + "A single patch file can contain changes to multiple files."
    )
    final_instruction = (
        "I need you to solve the provided issue by generating a single patch file that I can apply "
        + "directly to this repository using git apply. Please respond with a single patch "
        + "file in the format shown above."
    )
    problem_statement = instance["problem_statement"]
    final_text = [
        premise,
        "<issue>",
        problem_statement,
        "</issue>",
        "",
        "<code>",
        readmes_text,
        code_text,
        "</code>",
        "",
        example_explanation,
        PATCH_INSTRUCTIONS,
        "<patch>",
        PATCH_EXAMPLE,
        "</patch>",
        "",
        final_instruction,
        "Respond below:",
    ]
    final_text = "\n".join(final_text)
    return final_text


def full_file_gen(instance):
    premise = "You will be provided with a partial code base and an issue statement explaining a problem to resolve."
    readmes_text = make_code_text(instance["readmes"], add_line_numbers=False)
    code_text = make_code_text(instance["file_contents"], add_line_numbers=False)
    instructions = (
        "I need you to solve this issue by regenerating the full files in the code base that you would like to change. "
        + "You can change as many files as you like. "
        + "Please respond with a list of files and their revised contents in the following format."
    )
    problem_statement = instance["problem_statement"]
    final_text = [
        premise,
        "<issue>",
        problem_statement,
        "</issue>",
        "<code>",
        readmes_text,
        code_text,
        "</code>",
        instructions,
        "<example>",
        FULL_GENERATION_EXAMPLE,
        "</example>",
    ]
    final_text = "\n".join(final_text)
    return final_text


def ingest_files(filenames):
    files_dict = dict()
    for filename in filenames:
        with open(filename) as f:
            content = f.read()
        files_dict[filename] = content
    return files_dict


PROMPT_FUNCTIONS = {
    "style-2": prompt_style_2,
    "style-3": prompt_style_3,
    "full_file_gen": full_file_gen,
    "style-2-edits-only": prompt_style_2_edits_only,
    "style-3-fixed": prompt_style_3_fixed,
}


def add_retrieval_results(input_instances, retrieval_file, k, file_source):
    """
    Adds retrieval results to input_instances in-place
    """
    retrieval_results_path = Path(retrieval_file)
    assert retrieval_results_path.exists(), (
        f"Retrieval results not found at {retrieval_results_path}"
    )
    retrieval_results = [json.loads(line) for line in open(retrieval_results_path)]
    retrieval_results = {x["instance_id"]: x["hits"] for x in retrieval_results}
    for instance_id, instance in tqdm(
        input_instances.items(),
        total=len(input_instances),
        desc="Adding retrieval results",
    ):
        try:
            instance["hits"] = retrieval_results[instance_id][:k]
        except KeyError:
            logger.warning(f"Instance {instance_id} not found in retrieval results")
            instance["hits"] = list()


def get_oracle_filenames(instance):
    """
    Returns the filenames that are changed in the patch
    """
    source_files = {
        patch_file.source_file.split("a/", 1)[-1]
        for patch_file in unidiff.PatchSet(instance["patch"])
    }
    gold_docs = set()
    for source_file in source_files:
        gold_docs.add(source_file)
    return gold_docs


def add_text_inputs(
    instances,
    retrieval_file,
    k,
    prompt_style,
    file_source,
    max_context_len=None,
    tokenizer_name=None,
    verbose=False,
    progress_file=None,
    copy_repo_from_host_path=None,
) -> None:
    """Process instances and save results to progress file.

    Args:
    - instances: dictionary with unprocessed input instances
    - retrieval_file: if using retrieval method for file_contents, specify retrieval_file
    - k: if using retrieval, specifies the maximum number of files to include
    - prompt_style: specify the function to generate instructions and prompt
    - file_source: where to collect file_contents (e.g. oracle or bm25)
    - verbose: set ContextManager verbose to True
    - progress_file: required, path to save processed instances
    """
    assert progress_file is not None, "progress_file is required"

    # Create progress file directory if it doesn't exist
    progress_path = Path(progress_file)
    progress_path.parent.mkdir(parents=True, exist_ok=True)

    # Load already processed instances
    processed_ids = set()
    file_exists = os.path.exists(progress_file)

    if file_exists:
        with open(progress_file) as f:
            for line in f:
                instance = json.loads(line)
                processed_ids.add(instance["instance_id"])
        logger.info(f"Found {len(processed_ids)} already processed instances")
        progress_file_handle = open(progress_file, "a")
    else:
        progress_file_handle = open(progress_file, "w")

    try:
        if max_context_len is not None:
            assert tokenizer_name is not None, (
                "Must specify tokenizer_name if using max_context_len"
            )
            tokenizer, tokenizer_func = TOKENIZER_FUNCS[tokenizer_name]

        # Add retrieval results if needed
        if file_source in {"bm25"}:
            instances = deepcopy(instances)
            add_retrieval_results(instances, retrieval_file, k, file_source)

        # Filter out already processed instances
        instances_to_process = {
            k: v for k, v in instances.items() if k not in processed_ids
        }
        logger.info(f"Processing {len(instances_to_process)} instances")

        orig_dir = os.getcwd()
        with TemporaryDirectory(
            dir="/scratch" if os.path.exists("/scratch") else "/tmp"
        ) as root_dir:
            for instance_id, instance in tqdm(
                instances_to_process.items(),
                total=len(instances_to_process),
                desc="Processing instances",
            ):
                try:
                    with AutoContextManager(instance, root_dir, verbose=verbose,
                                             copy_repo_from_host_path=copy_repo_from_host_path) as cm:
                        # Process instance
                        processed_instance = deepcopy(instance)

                        # Add readmes
                        readmes = cm.get_readme_files()
                        processed_instance["readmes"] = ingest_files(readmes)

                        # Handle file contents based on configuration
                        if max_context_len is not None:
                            processed_instance["file_contents"] = dict()
                            base_text_inputs = PROMPT_FUNCTIONS[prompt_style](
                                processed_instance
                            )
                            base_text_input_length = len(
                                tokenizer_func(base_text_inputs, tokenizer)
                            )

                        if file_source == "oracle":
                            processed_instance["file_contents"] = ingest_files(
                                get_oracle_filenames(processed_instance)
                            )
                        elif file_source == "bm25":
                            processed_instance["file_contents"] = ingest_files(
                                [x["docid"] for x in processed_instance["hits"]]
                            )
                        elif file_source == "all":
                            processed_instance["file_contents"] = (
                                ingest_directory_contents(cm.repo_path)
                            )
                        elif file_source == "none":
                            processed_instance["file_contents"] = dict()
                        else:
                            raise ValueError(f"Invalid file source {file_source}")

                        # Handle context length limits
                        if max_context_len is not None:
                            cur_input_len = base_text_input_length
                            include_files = []
                            for filename in [
                                x["docid"] for x in processed_instance["hits"]
                            ]:
                                content = make_code_text(
                                    {
                                        filename: processed_instance["file_contents"][
                                            filename
                                        ]
                                    }
                                )
                                if tokenizer_name == "llama":
                                    tokens = tokenizer_func("\n" + content, tokenizer)
                                    idx = tokens.index(13)
                                    tokens = tokens[idx + 1 :]
                                else:
                                    tokens = tokenizer_func(content, tokenizer)
                                if cur_input_len + len(tokens) < max_context_len:
                                    include_files.append(filename)
                                    cur_input_len += len(tokens)
                            processed_instance["file_contents"] = {
                                filename: processed_instance["file_contents"][filename]
                                for filename in include_files
                            }

                        # Generate final text inputs
                        processed_instance["text"] = PROMPT_FUNCTIONS[
                            prompt_style
                        ](processed_instance)

                        # Save to progress file
                        progress_file_handle.write(
                            json.dumps(processed_instance, cls=DateTimeEncoder) + "\n"
                        )
                        progress_file_handle.flush()

                except Exception as e:
                    print(f"Failed on instance {instance_id}", e)
                    traceback.print_exc()
                    # Save failed instance
                    failed_instance = {**instance, "text": None}
                    progress_file_handle.write(json.dumps(failed_instance, cls=DateTimeEncoder) + "\n")
                    progress_file_handle.flush()
                finally:
                    os.chdir(orig_dir)
        os.chdir(orig_dir)
    finally:
        progress_file_handle.close()

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)
