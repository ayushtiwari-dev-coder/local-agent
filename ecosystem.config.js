module.exports = {
  apps : [{
    name: "local-agent",
    script: "main.py",
    interpreter: "python",
    args: "--mode telegram",
    autorestart: true
  }]
}