"""路由包：集中注册所有蓝图。"""


def register_blueprints(app):
    from routes.auth import auth_bp
    from routes.components import components_bp
    from routes.categories import categories_bp
    from routes.suppliers import suppliers_bp
    from routes.locations import locations_bp
    from routes.transactions import transactions_bp
    from routes.users import users_bp
    from routes.stats import stats_bp
    from routes.bom import bom_bp
    from routes.boms import boms_bp
    from routes.expenses import expenses_bp
    from routes.utility_bills import utility_bp
    from routes.maintenances import maintenances_bp
    from routes.api_tokens import tokens_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(components_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(bom_bp)
    app.register_blueprint(boms_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(utility_bp)
    app.register_blueprint(maintenances_bp)
    app.register_blueprint(tokens_bp)
