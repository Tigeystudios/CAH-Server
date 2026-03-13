import os
from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room
import random
import string

with open("questions", "r") as QF:
    QUESTIONS = QF.read().splitlines()
with open("answers", "r") as AF:
    ANSWERS = AF.read().splitlines()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'CHIPI_CHIPI_CHAPA_CHAPA_123'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

rooms = {}

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase, k=4))

def new_round(code):
    room = rooms[code]
    room["submissions"] = []

    emit("reset_gui", {}, to=code)

    judge_sid = room["player_order"][room["judge_index"]]
    room["current_judge"] = judge_sid
    current_question = random.choice(room["active_questions"])

    for sid in room["players"]:
        if sid == judge_sid:
            emit("is_judge", {"question": random.choice(room["active_questions"])}, to=sid)
        else:
            phand = room["players"][sid]["hand"]
            while len(phand) < 10:
                if room["active_answers"]:
                    phand.append(room["active_answers"].pop())
                else:
                    break
            emit("current_hand", {"hand": phand}, to=sid)

    emit("new_round", {"question": current_question}, to=code)

    room["judge_index"] = (room["judge_index"] + 1) % len(room["player_order"])

@socketio.on('create_room')
def on_create():
    code = generate_room_code()
    while code in rooms:
        code = generate_room_code()

    rooms[code] = {
        "host_id": request.sid,
        "players": {},
        "player_order": [],
        "judge_index": 0,
        "active_questions": QUESTIONS[:],
        "active_answers": ANSWERS[:],
        "black_card": "",
        "submissions": []
    }
    join_room(code)
    emit('room_created', {'code': code})
    print(f"Room {code} created for Host: {request.sid}")

@socketio.on('join_game')
def on_join(data):
    code = data.get('code')
    username = data.get('username').strip()

    if code in rooms and username != "":
        if len(rooms[code]["players"]) > 10:
            print(f"too many players: {len(rooms[code]["players"])}")
            return
        else:
            join_room(code)
            rooms[code]["players"][request.sid] = {
                "name": username,
                "score": 0,
                "hand": []
            }
    else:
        return

    emit('player_joined', {'name': username, 'id': request.sid}, to=code)
    emit('join_success', {'username': username})
    print(f"{username} joined room {code}")

@socketio.on("start_game")
def on_start_game(data):
    code = data["code"]
    room = rooms[code]

    emit("reset_gui", {}, to=code)

    if len(room["players"]) < 3:
        print(f"too little players: {len(room['players'])}")
        return

    room["player_order"] = list(room["players"].keys())
    random.shuffle(room["player_order"])
    room["judge_index"] = 0
    random.shuffle(room["active_answers"])

    new_round(code)

@socketio.on("submit_card")
def on_submit_card(data):
    code = data.get("code")
    room = rooms[code]
    card = data.get("card")

    room["submissions"].append({
        "username": data.get("username"),
        "card": card
        })

    room["players"][request.sid]["hand"].remove(card)

    emit("update_submissions", {"count": len(room["submissions"])}, to=code)
    emit("submission_received", to=request.sid)

    if len(room["submissions"]) == len(room["players"]) - 1:
        judge_sid = room["current_judge"]
        display_subs = room["submissions"][:]
        random.shuffle(display_subs)
        emit("judge_reveal", {"submissions": display_subs}, to=judge_sid)

def get_leaderboard(room):
        leaderboard = []
        for sid in room["players"]:
            player = room["players"][sid]
            leaderboard.append({"name": player["name"], "score": player["score"]})
        return leaderboard

@socketio.on("pick_winner")
def on_pick_winner(data):
    code = data.get("code")
    room = rooms[code]

    if not room or not room["submissions"]: return

    winner_name = data.get("winner_name")

    for sid in room["players"]:
        if room["players"][sid]["name"] == winner_name:
            room["players"][sid]["score"] += 1
            break

    room["submissions"] = []

    leaderboard = get_leaderboard(room)

    game_done = False
    for sid in room["players"]:
        if room["players"][sid]["score"] >= 5:
            game_done = True
            break
    
    if game_done:
        emit('game_over', {'winner_name': winner_name}, to=code)
        emit('player_results', to=code)
    else:
        emit("round_over", {"winner": winner_name, "leaderboard": leaderboard}, to=code)
        rooms[code]["judge_index"] = (rooms[code]["judge_index"] + 1) % len(rooms[code]["player_order"])
        
        socketio.sleep(10)
        
        new_round(code)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    socketio.run(app, host='0.0.0.0', port=port, debug=True, allow_unsafe_werkzeug=True)
