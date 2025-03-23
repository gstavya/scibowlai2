from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from firebase_config import auth
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import main3
from firebase_admin import credentials, firestore
import requests

db = firestore.client()

app = Flask(__name__)
app.secret_key = "your_secret_key"

login_manager = LoginManager()
login_manager.init_app(app)

FIREBASE_API_KEY = "AIzaSyCFMTmR7MttOxfPf9rFWd1NfgFsFuc509E"

class User(UserMixin):
    def __init__(self, uid, email):
        self.id = uid
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    email = session.get("email")
    if email:
        return User(user_id, email)
    return None

def sign_in_with_email_and_password(email, password):
    """Authenticate user with Firebase Authentication REST API."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        return response.json()
    else:
        return None

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user_data = sign_in_with_email_and_password(email, password)

        if user_data:
            user = User(user_data["localId"], email)
            login_user(user) 

            session["user_token"] = user_data["idToken"]
            session["user_id"] = user_data["localId"]
            session["email"] = email

            flash("Login successful!", "success")
            return redirect(url_for("question"))
        else:
            flash("Invalid email or password. Please try again.", "danger")
    
    return render_template("login.html")

# ✅ Register Page
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]  # Ensure password field exists in register.html
        try:
            user = auth.create_user(email=email, password=password)
            db = firestore.client()
            doc_ref = db.collection('users').document(email)
            doc_ref.set({"points": 0, "questionsAnswered": 0, "questionsCorrect": 0, "avgPercentQuestionSeen": 0})
            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception:
            flash("Error creating account. Try a different email.", "danger")
    return render_template("register.html")

@app.route("/logout")
def logout():
    logout_user()
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

@app.route("/question")
@login_required
def question():
    return render_template("question.html")

import requests

def get_groq_chat_completion(user_answer, correct_answer):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": "Bearer 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",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "llama3-70b-8192",   # Correct Groq model
        "messages": [
            {
                "role": "user",
                "content": f'Verify if this answer: "{user_answer}" matches the correct answer: "{correct_answer}". '
                           f'It does not have to be a precise match. It simply has to have the same idea. '
                           f'Respond with only "correct" or "wrong". For multiple choice answers, the user simply has to have the correct option (W, X, Y, or Z).'
            }
        ],
    }
    
    response = requests.post(url, json=data, headers=headers)  # Send correct JSON data
    if response.status_code == 200:
        reply = response.json()["choices"][0]["message"]["content"].strip().lower()
        return "correct" in reply
    else:
        print("No", response.status_code, response.text)
        return False
        
@app.route("/statistics")
@login_required
def statistics():
    email = session.get("email")  # Get the logged-in user's email
    if not email:
        flash("You must be logged in to view statistics.", "danger")
        return redirect(url_for("login"))

    user_ref = db.collection("users").document(email)
    user_doc = user_ref.get()

    if user_doc.exists:
        stats = user_doc.to_dict()
    else:
        stats = {
            "percentQuestionsSeen": 0,
            "points": 0,
            "questionsAnswered": 0,
            "questionsCorrect": 0
        }

    return render_template("statistics.html", stats=stats)

@app.route("/generate_question", methods=["GET", "POST"])
def generate_question():
    if request.method == "GET":
        # Get the category from the URL query parameter
        category = request.args.get("category")
        if not category:
            return jsonify({"error": "Category is required"}), 400

    elif request.method == "POST":
        # Get the category from the JSON body
        category = request.json.get("category")
        if not category:
            return jsonify({"error": "Category is required"}), 400

    # Call your method to fetch a question
    full_question = main3.find_question(category)
    print(full_question)

    # Split toss-up and bonus
    tossup_start = full_question.find("**TOSSUP")
    bonus_start = full_question.find("**BONUS")

    tossup = full_question[tossup_start:bonus_start].strip()
    bonus = full_question[bonus_start:].strip()

    # Extract answers
    if(tossup.find("ANSWER:")==-1):
        tossup_answer = tossup.split("Answer:")[-1].strip()
    else:
        tossup_answer = tossup.split("ANSWER:")[-1].strip()
    if(bonus.find("ANSWER:")==-1):
        bonus_answer = bonus.split("Answer:")[-1].strip()
    else:
        bonus_answer = bonus.split("ANSWER:")[-1].strip()

    if(tossup.find("ANSWER:")==-1):
        tossup_no_answer = tossup.split("Answer:")[0].strip()
    else:
        tossup_no_answer = tossup.split("ANSWER:")[0].strip()
    if(bonus.find("ANSWER:")==-1):
        bonus_no_answer = bonus.split("Answer:")[0].strip()
    else:
        bonus_no_answer = bonus.split("ANSWER:")[0].strip()

    return jsonify({
        "tossup": tossup_no_answer,
        "tossup_answer": tossup_answer,
        "bonus": bonus_no_answer,
        "bonus_answer": bonus_answer
    })

@app.route('/check_answer', methods=['POST'])
def check_answer():
    """Check the answer and update Firestore statistics."""
    data = request.json
    user_answer = data.get("user_answer", "").strip().lower()
    correct_answer = data.get("correct_answer", "").strip().lower()

    is_correct = get_groq_chat_completion(user_answer, correct_answer)

    # Get the current user
    email = session.get("email")
    if not email:
        return jsonify({"error": "User not authenticated"}), 401

    # Reference to the user's document in Firestore
    user_ref = db.collection("users").document(email)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()

        # Increment total questions answered
        questions_answered = user_data.get("questionsAnswered", 0) + 1
        questions_correct = user_data.get("questionsCorrect", 0)

        # Increment questionsCorrect if the answer is correct
        if is_correct:
            questions_correct += 1

        # Update Firestore with the new statistics
        user_ref.update({
            "questionsAnswered": questions_answered,
            "questionsCorrect": questions_correct
        })

    return jsonify({"correct": is_correct})


@app.route('/update_points', methods=['POST'])
def update_points():
    """Update points and ensure statistics are updated properly."""
    data = request.json
    new_score = data.get("increment", 0)

    email = session.get("email")
    if not email:
        return jsonify({"error": "User not authenticated"}), 401

    # Reference to the user's document
    user_ref = db.collection("users").document(email)
    user_doc = user_ref.get()

    if user_doc.exists:
        user_data = user_doc.to_dict()

        # Update points
        current_points = user_data.get("points", 0)
        updated_points = current_points + new_score

        # Update Firestore
        user_ref.update({"points": updated_points})

        return jsonify({
            "message": "Points and statistics updated successfully",
            "new_points": updated_points
        })
    else:
        return jsonify({"error": "User not found"}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
