'''
for each jsonl file in the directory, read the file, and for each line
extract from json 'problem_statement'
check if bug or fix is in this text
if bug or fix, add to bug list
if feature add to feature list
if refactor add to refactor list
print the lists counts
'''

import os
import json
import argparse
import glob
bug_words=['bug', 'fix', 'error']
feature_words=['feature', 'new']
refactor_words=['refactor', 'rewrite']

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_pattern", type=str, required=True)
    args = parser.parse_args()

    bug_list = []
    feature_list = []
    refactor_list = []

    for file in glob.glob(args.input_pattern, recursive=True):
        with open(file, "r") as f:
            for line in f:
                data = json.loads(line)
                if "problem_statement" in data:
                    if any(word in data["problem_statement"].lower() for word in bug_words):
                        bug_list.append(data)
                    elif any(word in data["problem_statement"].lower() for word in feature_words):
                        feature_list.append(data)
                    elif any(word in data["problem_statement"].lower() for word in refactor_words):
                        refactor_list.append(data)

    print(f"Bug number: {len(bug_list)}")
    print(f"Feature number: {len(feature_list)}")
    print(f"Refactor number: {len(refactor_list)}")

if __name__ == "__main__":
    main()