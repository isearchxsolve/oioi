const express = require('express')
const cors = require('cors')
const jwt = require('jsonwebtoken')
const bcrypt = require('bcryptjs')
const Database = require('better-sqlite3')

const app = express()
const db = new Database('app.db')
const SECRET = process.env.JWT_SECRET || 'change-me'

db.exec(`CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password TEXT)`)
db.exec(`CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, name TEXT, description TEXT, status TEXT DEFAULT 'created', created_at INTEGER DEFAULT (unixepoch()))`)

app.use(cors()); app.use(express.json())

const auth = (req, res, next) => {
  const h = req.headers.authorization
  if (!h) return res.status(401).json({error: 'Unauthorized'})
  try { req.user = jwt.verify(h.replace('Bearer ', ''), SECRET); next() }
  catch { res.status(401).json({error: 'Invalid token'}) }
}

app.get('/api/health', (_, res) => res.json({status: 'ok'}))

app.post('/api/auth/register', async (req, res) => {
  const { email, password } = req.body
  try {
    const hash = await bcrypt.hash(password, 12)
    const { lastInsertRowid: id } = db.prepare('INSERT INTO users (email, password) VALUES (?,?)').run(email, hash)
    res.json({ token: jwt.sign({sub: id, email}, SECRET, {expiresIn: '24h'}) })
  } catch { res.status(400).json({error: 'Email taken'}) }
})

app.post('/api/auth/login', async (req, res) => {
  const { email, password } = req.body
  const user = db.prepare('SELECT * FROM users WHERE email=?').get(email)
  if (!user || !await bcrypt.compare(password, user.password)) return res.status(401).json({error:'Invalid credentials'})
  res.json({ token: jwt.sign({sub: user.id, email}, SECRET, {expiresIn: '24h'}) })
})

app.get('/api/projects', auth, (req, res) => {
  res.json(db.prepare('SELECT * FROM projects WHERE owner_id=?').all(req.user.sub))
})

app.post('/api/projects', auth, (req, res) => {
  const { name, description } = req.body
  const { lastInsertRowid: id } = db.prepare('INSERT INTO projects (owner_id, name, description) VALUES (?,?,?)').run(req.user.sub, name, description || '')
  res.status(201).json(db.prepare('SELECT * FROM projects WHERE id=?').get(id))
})

const PORT = process.env.PORT || 8000
app.listen(PORT, () => console.log(`Server running on port ${PORT}`))
