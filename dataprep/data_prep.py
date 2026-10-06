"""
data preparation for the ai-generated content detection project
this file takes the daigt v2 dataset and the hc3 dataset, makes their
columns/labels consistent, cleans the text and combines them into one file
generates graphs for word count, word length, type token ratio and contraciton rate 
"""
from pathlib import Path
import json
import re
import sys
import pandas as pd
import matplotlib.pyplot as plt

DATA_DIR = Path(__file__).resolve().parent
#the raw daigt csv may sit next to this file or in the archive/ subfolder
DAIGT_FILE = next((p for p in (DATA_DIR / "train_v2_drcat_02.csv",
                               DATA_DIR / "archive" / "train_v2_drcat_02.csv") if p.exists()),
                  DATA_DIR / "train_v2_drcat_02.csv")
HC3_FILE = DATA_DIR / "all.jsonl"

OUTPUT_FILE = DATA_DIR / "merged_dataset.csv"
PLOT_DIR = DATA_DIR / "eda_plots"

def clean_text(value):
    """
    clean up small formatting problems in text sample
    this does not rewrite the answer or try to change its meaning
    it only removes formatting issues that can make later processing harder
    """
    #replace nan values with ""
    if pd.isna(value):
        return ""
    text = str(value)
    #remove null characters 
    text = text.replace("\x00", " ")
    #convert tabs and repeated spaces into one normal space
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    #avoid lots of blank lines while keeping paragraph breaks readable
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def generator_family(name):
    """
    group the many generator names into a few model families, by name only
    this lets person c hold out a whole family (e.g. every llama variant)
    """
    name = str(name).lower()
    if name == "human":
        return "human"
    for family in ("gpt", "llama", "mistral", "palm", "claude", "falcon", "cohere"):
        if family in name:
            return family
    return "other"

def load_daigt(file_path):
    """
    load daigt v2 and convert it to the same column layout used for hc3
    daigt already has a text column and a label column so most of the work
    is selecting the useful fields and giving the source/topic clear names
    """
    print(f"loading DAIGT dataset from: {file_path}")
    #read the csv into a pandas dataframe so we can select and clean columns
    daigt = pd.read_csv(file_path)
    #check that the important columns exist before trying to use them
    required_columns = {"text", "label"}
    missing_columns = required_columns - set(daigt.columns)
    if missing_columns:
        raise ValueError(f"DAIGT is missing required columns: {missing_columns}")
    #keep only the fields needed
    daigt = daigt.copy()
    #the raw source column names the writer (persuade_corpus for humans, the llm name for ai rows)
    #keep it as generator before source is overwritten with the dataset name
    daigt["generator"] = daigt["source"].fillna("unknown") if "source" in daigt.columns else "unknown"
    daigt["source"] = "DAIGT_v2"
    if "prompt_name" in daigt.columns:
        daigt["topic"] = daigt["prompt_name"].fillna("unknown")
    else:
        daigt["topic"] = "unknown"
    #use one consistent format for all datasets:
    #text = the writing sample, label = 0 human / 1 ai
    #source = which dataset it came from topic = topic or prompt
    #one group id per essay so no essay can land on both sides of a train/test split
    daigt["group"] = ["daigt_" + str(i) for i in range(len(daigt))]
    daigt = daigt[["text", "label", "source", "topic", "group", "generator"]]
    #convert labels to numbers
    daigt["label"] = pd.to_numeric(daigt["label"], errors="coerce")
    daigt["text"] = daigt["text"].apply(clean_text)
    #only keep rows with a valid binary label and some actual text
    daigt = daigt[daigt["label"].isin([0, 1]) & daigt["text"].str.len().gt(0)].copy()
    daigt["label"] = daigt["label"].astype(int)
    daigt.loc[daigt["label"] == 0, "generator"] = "human"
    print(f"DAIGT rows after cleaning: {len(daigt):,}")
    return daigt

def load_hc3(file_path):
    """
    load hc3 jsonl and turn its question/answer structure into rows
    0 = human-written 1 = ai-generated
    """
    print(f"loading HC3 dataset from: {file_path}")
    rows = []
    with open(file_path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print(f"Warning: could not parse HC3 line {line_number}; skipping it.")
                continue
            #keep the question/source as metadata so we can examine data
            #from different topics or hc3 subsets later
            question = clean_text(record.get("question", ""))
            #answers to the same question share a group so they stay on the same side of a split
            group_id = f"hc3_{line_number}"
            topic = clean_text(record.get("source", "unknown")) or "unknown"
            human_answers = record.get("human_answers", [])
            ai_answers = record.get("chatgpt_answers", [])
            if not isinstance(human_answers, list):
                human_answers = []
            if not isinstance(ai_answers, list):
                ai_answers = []
            #add each human answer as its own row, using label 0
            for answer in human_answers:
                answer = clean_text(answer)
                if answer:
                    rows.append({"text": answer,"label": 0,"source": "HC3","topic": topic,"group": group_id,"generator": "human"})
            #add each ai answer as its own row, using label 1
            for answer in ai_answers:
                answer = clean_text(answer)
                if answer:
                    rows.append({"text": answer,"label": 1,"source": "HC3","topic": topic,"group": group_id,"generator": "chatgpt"})
    #turn the list of answer rows into a dataframe with the same columns as daigt
    hc3 = pd.DataFrame(rows, columns=["text", "label", "source", "topic", "group", "generator"])
    print(f"HC3 answer rows after cleaning: {len(hc3):,}")
    return hc3

def extract_text_features(text):
    """
    calculate basic writing style features for one text sample
    these features are calculated inside this file
    """
    #split the text into words
    words = re.findall(r"\b\w+\b", str(text).lower())
    word_count = len(words)
    if word_count == 0:
        average_word_length = 0
        type_token_ratio = 0
    else:
        average_word_length = sum(len(word) for word in words) / word_count
        type_token_ratio = len(set(words)) / word_count
    #count common contractions such as don't, can't and it's
    contractions = re.findall(r"\b\w+(?:'|’)\w+\b",str(text).lower())
    contraction_rate = len(contractions) / max(word_count, 1)
    return {
        "n_words": word_count,
        "avg_word_len": average_word_length,
        "type_token_ratio": type_token_ratio,
        "contraction_rate": contraction_rate,
    }

def create_eda_plots(dataset, output_dir):
    """
    make a few data analysis plots
    we calculate the features using the projects existing features
    class so the plots use the same feature definitions as the detector
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    print("calculating text features for EDA plots...")
    #calculate the same basic features locally for each text sample
    #each result is a dictionary of values such as word count and word length
    feature_rows = dataset["text"].apply(extract_text_features)
    features = pd.DataFrame(feature_rows.tolist())
    features["label"] = dataset["label"].to_numpy()
    #save a small numeric summary as a csv for the report
    summary = features.groupby("label").describe().transpose()
    summary.to_csv(output_dir / "feature_summary.csv")
    #these names are the feature name expected
    #each plot compares the distribution for human vs ai samples
    plot_features = [
        ("n_words", "Word count", "word_count_distribution.png"),
        ("type_token_ratio", "Type-token ratio", "type_token_ratio.png"),
        ("avg_word_len", "Average word length", "average_word_length.png"),
        ("contraction_rate", "Contraction rate", "contraction_rate.png"),
    ]
    for feature_name, plot_title, file_name in plot_features:
        if feature_name not in features.columns:
            print(f"Skipping {plot_title}: feature '{feature_name}' was not found.")
            continue
        plt.figure(figsize=(9, 5))
        #plot label 0 and label 1 separately so their distributions can be compared
        for label, label_name in [(0, "Human"), (1, "AI")]:
            values = features.loc[features["label"] == label, feature_name].dropna()
            if feature_name == "n_words" and not values.empty:
                upper_limit = values.quantile(0.99)
                values = values.clip(upper=upper_limit)
            plt.hist(values, bins=40, alpha=0.55, label=label_name)
        plt.title(plot_title)
        plt.xlabel(plot_title)
        plt.ylabel("Number of samples")
        plt.legend()
        plt.tight_layout()
        #save each chart to disk
        plt.savefig(output_dir / file_name, dpi=150)
        plt.close()
    print(f"EDA plots and summary saved to: {output_dir}")

def main():
    """
    run the full preparation process in the correct order
    """
    if not DAIGT_FILE.exists():
        raise FileNotFoundError(f"Could not find DAIGT file: {DAIGT_FILE}\n""Place train_v2_drcat_02.csv inside backend/ml/data/.")
    if not HC3_FILE.exists():
        raise FileNotFoundError(f"Could not find HC3 file: {HC3_FILE}\n""Place all.jsonl inside backend/ml/data/.")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    daigt = load_daigt(DAIGT_FILE)
    hc3 = load_hc3(HC3_FILE)
    print("combining DAIGT and HC3...")
    #both datasets now use the same column names and label convention so they can be stacked together 
    merged = pd.concat([daigt, hc3], ignore_index=True)
    merged["generator_family"] = merged["generator"].apply(generator_family)
    #remove exact duplicate text/label pairs
    #we keep the same text if it appears once as human and once as ai
    before_deduplication = len(merged)
    merged = merged.drop_duplicates(subset=["text", "label"]).reset_index(drop=True)
    removed = before_deduplication - len(merged)
    print(f"Removed duplicate text/label rows: {removed:,}")
    #save the cleaned merged dataset
    merged.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"saved merged dataset: {OUTPUT_FILE}")
    print(f"rotal rows: {len(merged):,}")
    print("label counts (0=human, 1=AI):")
    print(merged["label"].value_counts().sort_index())
    #generate eda charts after saving the main dataset
    if "--skip-eda" not in sys.argv:
        create_eda_plots(merged, PLOT_DIR)

if __name__ == "__main__":
    main()
