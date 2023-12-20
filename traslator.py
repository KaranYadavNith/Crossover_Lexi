# -*- coding: utf-8 -*-
"""Traslator.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1_Inby80bWxVX5IO6xulZu-GbMHFUL2lp
"""

!pip install transformers sentencepiece datasets
!pip install sentencepiece

from datasets import load_dataset
from google.colab import drive
from IPython.display import display
from IPython.html import widgets
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import torch
from torch import optim
from torch.nn import functional as F
from transformers import AdamW, AutoModelForSeq2SeqLM, AutoTokenizer
from transformers import get_linear_schedule_with_warmup
from tqdm import tqdm_notebook
sns.set()

from transformers import AutoModelForSeq2SeqLM
model_repo = 'Helsinki-NLP/opus-mt-hi-en'
model = AutoModelForSeq2SeqLM.from_pretrained(model_repo)
max_seq_len = model.config.max_length
device = torch.device("cuda")
model.cuda()

!pip install sentencepiece

tokenizer = AutoTokenizer.from_pretrained(model_repo)

input_sent = 'Here is our test sentence!'
token_ids = tokenizer.encode(input_sent, return_tensors='pt').to(device)  # Move to GPU
token_ids

model_out = model.generate(token_ids)
print(model_out)

output_text = tokenizer.convert_tokens_to_string(
    tokenizer.convert_ids_to_tokens(model_out[0].cpu().numpy()))  # Move to CPU for conversion
print(output_text)

# Read English sentences from "IITB.en-hi.en"
with open("/content/IITB.en-hi.en", "r", encoding="utf-8") as f:
    english_sentences = f.read().splitlines()

# Read Hindi sentences from "IITB.en-hi.hi"
with open("/content/IITB.en-hi.hi", "r", encoding="utf-8") as f:
    hindi_sentences = f.read().splitlines()

# Create a dictionary for the dataset
custom_dataset = {
    'translation': [{'hi': hin_sent, 'en': eng_sent} for hin_sent, eng_sent in zip(hindi_sentences, english_sentences)],
}

# Split your dataset into 'train' and 'test' splits if needed
split_ratio = 0.8  # Adjust as per your requirement
split_index = int(len(custom_dataset['translation']) * split_ratio)

train_dataset = {'translation': custom_dataset['translation'][:split_index]}
test_dataset = {'translation': custom_dataset['translation'][split_index:]}

# Example usage
for example in train_dataset['translation']:
    print("Hindi:", example['hi'])
    print("English:", example['en'])
    print()

LANG_TOKEN_MAPPING = {
    'hi': '<hi>',
    'en': '<en>'
}

# Replace 'Your example input string goes here' with an actual input string
example_input_str = 'Your example input string goes here'

# Encode the example input string
token_ids = tokenizer.encode(
    example_input_str, return_tensors='pt',
    padding='max_length',
    truncation=True, max_length=max_seq_len)

print(token_ids)

def encode_input_str(text, target_lang, tokenizer, seq_len,
                     lang_token_map=LANG_TOKEN_MAPPING):
  target_lang_token = lang_token_map[target_lang]

  # Tokenize and add special tokens
  input_ids = tokenizer.encode(
      text = target_lang_token + text,
      return_tensors = 'pt',
      padding = 'max_length',
      truncation = True,
      max_length = seq_len)

  return input_ids[0]

def encode_target_str(text, tokenizer, seq_len,
                      lang_token_map=LANG_TOKEN_MAPPING):
  token_ids = tokenizer.encode(
      text = text,
      return_tensors = 'pt',
      padding = 'max_length',
      truncation = True,
      max_length = seq_len)

  return token_ids[0]

def format_translation_data(translations, lang_token_map,
                            tokenizer, seq_len=128):
  # Choose a random 2 languages for in i/o
  langs = list(lang_token_map.keys())
  input_lang, target_lang = np.random.choice(langs, size=2, replace=False)

  # Get the translations for the batch
  input_text = translations[input_lang]
  target_text = translations[target_lang]

  if input_text is None or target_text is None:
    return None

  input_token_ids = encode_input_str(
      input_text, target_lang, tokenizer, seq_len, lang_token_map)

  target_token_ids = encode_target_str(
      target_text, tokenizer, seq_len, lang_token_map)

  return input_token_ids, target_token_ids

def transform_batch(batch, lang_token_map, tokenizer):
  inputs = []
  targets = []
  for translation_set in batch['translation']:
    formatted_data = format_translation_data(
        translation_set, lang_token_map, tokenizer, max_seq_len)

    if formatted_data is None:
      continue

    input_ids, target_ids = formatted_data
    inputs.append(input_ids.unsqueeze(0))
    targets.append(target_ids.unsqueeze(0))

  batch_input_ids = torch.cat(inputs).cuda()
  batch_target_ids = torch.cat(targets).cuda()

  return batch_input_ids, batch_target_ids

import itertools

def get_data_generator(translations, lang_token_map, tokenizer, batch_size=32):
    translations_copy = translations.copy()
    random.shuffle(translations_copy)
    translation_batches = [translations_copy[i:i + batch_size] for i in range(0, len(translations_copy), batch_size)]

    for raw_batch in itertools.cycle(translation_batches):
        yield transform_batch({'translation': raw_batch}, lang_token_map, tokenizer)

import random

# Assuming train_dataset is a dictionary with a 'translation' key
translations = train_dataset['translation']
random.shuffle(translations)

# Accessing the first example in the 'train' split
first_example = translations[0]

in_ids, out_ids = format_translation_data(first_example, LANG_TOKEN_MAPPING, tokenizer)

print(' '.join(tokenizer.convert_ids_to_tokens(in_ids)))
print(' '.join(tokenizer.convert_ids_to_tokens(out_ids)))

# Assuming test_dataset is a dictionary with a 'translation' key
test_translations = test_dataset['translation']
data_gen = get_data_generator(test_translations, LANG_TOKEN_MAPPING, tokenizer, 8)
data_batch = next(data_gen)
print('Input shape:', data_batch[0].shape)
print('Output shape:', data_batch[1].shape)

n_epochs = 5
batch_size = 10
print_freq = 50
checkpoint_freq = 1000
lr = 5e-4
n_batches = int(np.ceil(len(train_dataset) / batch_size))
total_steps = n_epochs * n_batches
n_warmup_steps = int(total_steps * 0.01)

optimizer = AdamW(model.parameters(), lr=lr)
scheduler = get_linear_schedule_with_warmup(
    optimizer, n_warmup_steps, total_steps)

def eval_model(model, gdataset, max_iters=8):
  test_generator = get_data_generator(gdataset, LANG_TOKEN_MAPPING,
                                      tokenizer, batch_size)
  eval_losses = []
  for i, (input_batch, label_batch) in enumerate(test_generator):
    if i >= max_iters:
      break

    model_out = model.forward(
        input_ids = input_batch,
        labels = label_batch)
    eval_losses.append(model_out.loss.item())

  return np.mean(eval_losses)

test_loss = eval_model(model, test_dataset)

for epoch_idx in range(n_epochs):
  # Randomize data order
  data_generator = get_data_generator(train_dataset, LANG_TOKEN_MAPPING,
                                      tokenizer, batch_size)

  for batch_idx, (input_batch, label_batch) \
      in tqdm_notebook(enumerate(data_generator), total=n_batches):

    optimizer.zero_grad()

    # Forward pass
    model_out = model.forward(
        input_ids = input_batch,
        labels = label_batch)

    loss = model_out.loss
    losses.append(loss.item())
    loss.backward()
      optimizer.step()
    scheduler.step()

    # Print training update info
    if (batch_idx + 1) % print_freq == 0:
      avg_loss = np.mean(losses[-print_freq:])
      print('Epoch: {} | Step: {} | Avg. loss: {:.3f} | lr: {}'.format(
          epoch_idx+1, batch_idx+1, avg_loss, scheduler.get_last_lr()[0]))

  test_loss = eval_model(model, test_dataset)
  print('Test loss of {:.3f}'.format(test_loss))

window_size = 50
smoothed_losses = []
for i in range(len(losses)-window_size):
  smoothed_losses.append(np.mean(losses[i:i+window_size]))

plt.plot(smoothed_losses[100:])

test_sentence = test_dataset[0]['translation']['en']
print('Raw input text:', test_sentence)

input_ids = encode_input_str(
    text = test_sentence,
    target_lang = 'hi',
    tokenizer = tokenizer,
    seq_len = model.config.max_length,
    lang_token_map = LANG_TOKEN_MAPPING)
input_ids = input_ids.unsqueeze(0).cuda()

print('Truncated input text:', tokenizer.convert_tokens_to_string(
    tokenizer.convert_ids_to_tokens(input_ids[0])))

output_tokens = model.generate(input_ids, num_beams=10, num_return_sequences=3)
# print(output_tokens)
for token_set in output_tokens:
  print(tokenizer.decode(token_set, skip_special_tokens=True))

# Provided information
sentence_0 = "It has been confirmed that eight thoroughbred race horses at Randwick Racecourse in Sydney have been infected with equine influenza."

# Given sequence with placeholders
sequence = "<extra_id_0> <extra_id_0>. <extra_id_0>.) <extra_id_10>.едет <extra_id_10> <extra_id_10>)on.on bulunduарамен次次ان次وا"

# Replace the placeholders with actual content
filled_sequence = sequence.replace("<extra_id_0>", sentence_0)
filled_sequence = filled_sequence.replace("<extra_id_10>", sentence_0)

print("Filled Sequence:", filled_sequence)

import nltk

def calculate_wer(reference, candidate):
    """
    Calculate Word Error Rate (WER) between reference and candidate.
    :param reference: list of reference words
    :param candidate: list of candidate words
    :return: Word Error Rate
    """
    align = nltk.edit_distance(reference, candidate)
    wer = align / len(reference)
    return wer

# Example usage:
reference_translation = ["your name"]
candidate_translation = ["Your name was asked, “What is your name?"]

wer_score = calculate_wer(reference_translation, candidate_translation)
print(f"Word Error Rate: {wer_score}")

import nltk
nltk.download('punkt')
from nltk.translate.bleu_score import sentence_bleu

reference = ["your name"]
candidate = 'Your name was asked, “What is your name?”'

# Tokenize the sentences
reference_tokens = [nltk.word_tokenize(sent) for sent in reference]
candidate_tokens = nltk.word_tokenize(candidate)

# Calculate BLEU score
bleu_score = sentence_bleu(reference_tokens, candidate_tokens)

print("BLEU Score:", bleu_score)

pip install rouge

from rouge import Rouge

# Reference (ground truth) and candidate (generated) sentences
reference = ["your name"]
candidate = "Your name was asked, 'What is your name?'"

# Convert the reference list to a string
reference_str = ' '.join(reference)

# Initialize the Rouge object
rouge = Rouge()

# Calculate ROUGE scores
scores = rouge.get_scores(candidate, reference_str)

# Print the ROUGE scores
print("ROUGE Scores:")
print("ROUGE-1 Precision:", scores[0]["rouge-1"]["p"])
print("ROUGE-1 Recall:", scores[0]["rouge-1"]["r"])
print("ROUGE-1 F1 Score:", scores[0]["rouge-1"]["f"])

print("ROUGE-2 Precision:", scores[0]["rouge-2"]["p"])
print("ROUGE-2 Recall:", scores[0]["rouge-2"]["r"])
print("ROUGE-2 F1 Score:", scores[0]["rouge-2"]["f"])

print("ROUGE-L Precision:", scores[0]["rouge-l"]["p"])
print("ROUGE-L Recall:", scores[0]["rouge-l"]["r"])
print("ROUGE-L F1 Score:", scores[0]["rouge-l"]["f"])

import nltk

# Download the WordNet dataset
nltk.download('wordnet')

import nltk
from nltk.translate import meteor_score

# Download the WordNet dataset
nltk.download('wordnet')

# Reference (ground truth) and candidate (generated) sentences
reference = ["your name"]
candidate = "Your name was asked, 'What is your name?'"

# Tokenize the sentences
reference_tokens = [nltk.word_tokenize(sent) for sent in reference]
candidate_tokens = nltk.word_tokenize(candidate)

# Calculate METEOR score
meteor_score_value = meteor_score.meteor_score(reference_tokens, candidate_tokens)

# Print the METEOR score
print("METEOR Score:", meteor_score_value)

