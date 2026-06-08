from flask import Flask


def create_api_app(bot_instance):
    from api.verify import verify_bp
    from api.assign_role import assign_role_bp
    app = Flask(__name__)
    app.register_blueprint(verify_bp)

    assign_role_bp.bot = bot_instance
    app.register_blueprint(assign_role_bp)
    return app
