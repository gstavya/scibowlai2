import re
import firebase_admin
from firebase_admin import credentials, firestore
from firebase_config import auth

# Reference to Firestore
db = firestore.client()

def find_question(category):
    doc_ref = db.collection('questions').document('sciencebowl')
    doc_snapshot = doc_ref.get()
    doc_data = doc_snapshot.to_dict()
    questions = doc_data[category]
    x = random.randint(0, len(questions) - 1)
    return questions[x]