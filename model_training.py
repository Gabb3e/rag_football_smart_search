from transformers import BartForConditionalGeneration, BartTokenizer, Trainer, TrainingArguments, EarlyStoppingCallback
from datasets import Dataset
import pandas as pd
import torch
from sklearn.model_selection import train_test_split
import torch.nn as nn

# Check if a GPU is available and use it
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Load pre-trained BART model and tokenizer
model = BartForConditionalGeneration.from_pretrained('facebook/bart-large', ignore_mismatched_sizes=True)
model.lm_head = nn.Linear(model.config.d_model, model.config.vocab_size)

# Freeze all layers in the model except the output head (lm_head)
for param in model.parameters():
    param.requires_grad = False  # Freeze all parameters

# Now, unfreeze only the last layer (output head) for fine-tuning
for param in model.lm_head.parameters():
    param.requires_grad = True  # Unfreeze the lm_head (output head)

# Unfreeze only the last few layers of the decoder for fine-tuning
for param in model.model.decoder.layers[-6:].parameters():
    param.requires_grad = True  # Unfreeze the last 3 layers of the decoder

model.to(device)  # Move the model to the device (GPU if available)
tokenizer = BartTokenizer.from_pretrained('facebook/bart-large')

# Load the dataset from a CSV file
df = pd.read_csv('query_answer_data.csv')

# Split the dataset into training and evaluation sets
train_df, eval_df = train_test_split(df, test_size=0.2)  # 80% train, 20% eval
train_dataset = Dataset.from_pandas(train_df)
eval_dataset = Dataset.from_pandas(eval_df)

# Tokenize the inputs and outputs
def tokenize_function(examples):
    inputs = examples['query']  # The queries (inputs)
    targets = examples['answer']  # The answers (outputs)
    
    # Tokenize inputs and targets (with truncation)
    model_inputs = tokenizer(inputs, max_length=512, truncation=True, padding="max_length")
    # Tokenize the targets using 'text_target'
    labels = tokenizer(text_target=targets, max_length=150, truncation=True, padding="max_length")
    model_inputs["labels"] = labels["input_ids"]

    return model_inputs

# Apply the tokenization to training and evaluation datasets
tokenized_train_dataset = train_dataset.map(tokenize_function, batched=True, remove_columns=train_dataset.column_names)
tokenized_eval_dataset = eval_dataset.map(tokenize_function, batched=True, remove_columns=eval_dataset.column_names)

# Convert the datasets to PyTorch format
tokenized_train_dataset.set_format("torch")
tokenized_eval_dataset.set_format("torch")

# Define training arguments
training_args = TrainingArguments(
    output_dir="./results",
    eval_strategy="epoch",
    save_strategy="epoch",  
    learning_rate=1e-6,
    per_device_train_batch_size=2,
    per_device_eval_batch_size=2,
    dataloader_num_workers=4,
    num_train_epochs=50,
    weight_decay=0.001,
    report_to="none",
    save_total_limit=4,  # Limit number of saved models
    save_steps=500,      # Save checkpoint every 500 steps
    load_best_model_at_end=True,  # Load the best model at the end
    metric_for_best_model="eval_loss",
    greater_is_better=False,  # Minimize loss
    gradient_accumulation_steps=4,  # Accumulate gradients over 4 steps
)

# Set up the Trainer
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_train_dataset,
    eval_dataset=tokenized_eval_dataset,
    callbacks=[EarlyStoppingCallback(early_stopping_patience=3)]
)

# Start the fine-tuning
trainer.train()

# Save the fine-tuned model for future use
model.save_pretrained("./fine_tuned_bart")
tokenizer.save_pretrained("./fine_tuned_bart")