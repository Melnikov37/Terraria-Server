from terraria_admin import create_app

app = create_app()

if __name__ == '__main__':
    print("=" * 50)
    print("Terraria Web Admin Panel")
    print("=" * 50)
    print("Access: http://0.0.0.0:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False)
