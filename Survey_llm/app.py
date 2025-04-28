from flask import Flask, render_template, request, redirect, session, Response
from markdown import markdown
from db_config import get_connection
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.tables import TableExtension
import csv

def render_markdown_safe(text):
    return markdown(text, extensions=[
        FencedCodeExtension(),
        CodeHiliteExtension(),
        TableExtension()
    ])
app = Flask(__name__, template_folder='templates')
app.secret_key = 'secret-key'

LEVEL_ORDER = {
    'Not familiar at all': 0,
    'Beginner': 1,
    'Moderate': 2,
    'Proficient': 3,
    'Very proficient': 4
}
@app.route('/')
def index():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM answers WHERE student_email = %s", (email,))
        user = cursor.fetchone()

        if user:
            student_id = user['id']
            cursor.execute("SELECT COUNT(*) as count FROM llm_feedback WHERE student_id = %s", (student_id,))
            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if result['count'] > 0:
                return redirect('/thankyou')
            else:
                session['student_id'] = student_id
                return redirect('/term')
        else:
            cursor.close()
            conn.close()
            return render_template("unregistered.html")

    return render_template('login.html')


# --- app.py (partial) ---

@app.route('/term', methods=['GET', 'POST'])
def term():
    student_id = session.get('student_id')
    if not student_id:
        return redirect('/login')

    selected_indices = get_selected_question_indices(student_id)
    return render_survey_route(questions_range=selected_indices, template='term.html')

@app.route('/coding', methods=['GET', 'POST'])
def coding():
    return render_survey_route(questions_range=[7], template='coding.html')

def get_selected_question_indices(student_id):
    conn = get_connection()  # 保留 conn 对象，防止被 GC 回收
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT java_programming, `SQL`, data_mining_and_machine_learning, IoT, HCI, blockchains
        FROM answers WHERE id = %s
    """, (student_id,))
    row = cursor.fetchone()

    cursor.close()
    conn.close()

    skill_levels = {
        'java_programming': LEVEL_ORDER.get(row['java_programming'], -1),
        'SQL': LEVEL_ORDER.get(row['SQL'], -1),
        'data_mining_and_machine_learning': LEVEL_ORDER.get(row['data_mining_and_machine_learning'], -1),
        'IoT': LEVEL_ORDER.get(row['IoT'], -1),
        'HCI': LEVEL_ORDER.get(row['HCI'], -1),
        'blockchains': LEVEL_ORDER.get(row['blockchains'], -1),
    }

    sorted_skills = sorted(skill_levels.items(), key=lambda x: x[1])
    lowest = [name for name, _ in sorted_skills[:2]]
    highest = [name for name, _ in sorted_skills[-2:]]

    skill_to_index = {
        'java_programming': 1,
        'SQL': 2,
        'data_mining_and_machine_learning': 3,
        'IoT': 4,
        'HCI': 5,
        'blockchains': 6,
    }

    return [skill_to_index[skill] for skill in lowest + highest]

def render_survey_route(questions_range, template):
    if 'student_id' not in session:
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    student_id = session['student_id']

    if request.method == 'POST':
        # for i in questions_range:
        for idx, qidx in enumerate(questions_range, start=1):
            qid = request.form.get(f'question_id_{idx}')
            # qid = request.form.get(f'question_id_{i}')
            pre = request.form.get(f'pre_score_{idx}')
            post = request.form.get(f'post_score_{idx}')
            ranks = [request.form.get(f'rank_{j}_{idx}') for j in range(1, 6)]

            cursor.execute("""
                INSERT INTO llm_feedback (student_id, question_id, initial_understanding,
                    llm_default_rank, llm_skills_rank, llm_hobbies_rank, llm_subjects_rank,
                    llm_all_rank, final_understanding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (student_id, qid, pre, *ranks, post))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect('/coding') if template == 'term.html' else redirect('/thankyou')

    cursor.execute("SELECT * FROM questions")
    questions = cursor.fetchall()

    cursor.execute("SELECT * FROM llm_response_default")
    default_responses = {
        row['question_id']: render_markdown_safe(row['response'])
        for row in cursor.fetchall()
    }

    cursor.execute("SELECT * FROM llm_response_skills WHERE student_id = %s", (student_id,))
    skills = cursor.fetchone()

    cursor.execute("SELECT * FROM llm_response_hobbies WHERE student_id = %s", (student_id,))
    hobbies = cursor.fetchone()

    cursor.execute("SELECT * FROM llm_response_subjects WHERE student_id = %s", (student_id,))
    subjects = cursor.fetchone()

    cursor.execute("SELECT * FROM llm_response_all WHERE student_id = %s", (student_id,))
    all_responses_data = cursor.fetchone()

    topic_fields = [
        'java_response', 'sql_response', 'data_mining_response', 'IOT_response',
        'HCI_response', 'blockchains_response', 'coding_response'
    ]

    all_responses = []
    for i in questions_range:
        q = questions[i - 1]
        qid = q['question_id']
        topic_field = topic_fields[i - 1]
        response = {
            'question': render_markdown_safe(q['question']),
            'question_id': qid,
            'default': render_markdown_safe(default_responses.get(qid, '')),
            'skills': render_markdown_safe(skills[topic_field]) if skills else '',
            'hobbies': render_markdown_safe(hobbies[topic_field]) if hobbies else '',
            'subjects': render_markdown_safe(subjects[topic_field]) if subjects else '',
            'all': render_markdown_safe(all_responses_data[topic_field]) if all_responses_data else ''
        }
        all_responses.append(response)

    cursor.close()
    conn.close()
    return render_template(template, responses=all_responses)

@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')

@app.route('/feedback')
def feedback():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM llm_feedback")
    feedbacks = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('feedback.html', feedbacks=feedbacks)

@app.route('/download_feedback')
def download_feedback():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM llm_feedback")
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    cursor.close()
    conn.close()

    def generate():
        data = [columns] + list(rows)
        for row in data:
            yield ','.join(str(item) if item is not None else '' for item in row) + '\n'

    return Response(
        generate(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=llm_feedback.csv'}
    )

if __name__ == '__main__':
    # app.run(debug=True)
    app.run(host='0.0.0.0', port=8080)