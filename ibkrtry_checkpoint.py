import pandas as pd
import json

class CheckpointManager:
    def __init__(self, checkpoint_file='checkpoint.json'):
        self.checkpoint_file = checkpoint_file
        
    def save_progress(self, completed_tickers, remaining_tickers):
        checkpoint = {
            'completed': completed_tickers,
            'remaining': remaining_tickers
        }
        with open(self.checkpoint_file, 'w') as f:
            json.dump(checkpoint, f)
            
    def load_progress(self):
        try:
            with open(self.checkpoint_file, 'r') as f:
                checkpoint = json.load(f)
                return checkpoint['completed'], checkpoint['remaining']
        except FileNotFoundError:
            return [], []