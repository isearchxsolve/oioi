def signup(email, password):
    return {'id': 'user_123', 'email': email}


def login(email, password):
    return {'token': 'session_token_abc', 'user_id': 'user_123'}


def create_project(token, name):
    return {'id': 'proj_456', 'name': name, 'owner_id': 'user_123'}