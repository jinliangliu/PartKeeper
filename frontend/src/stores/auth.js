import { reactive } from 'vue'

const TOKEN_KEY = 'partkeeper_token'
const USER_KEY = 'partkeeper_user'

function readUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export const authStore = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: readUser(),

  get isLoggedIn() {
    return !!this.token
  },

  get isAdmin() {
    return this.user?.role === 'admin'
  },

  setAuth(token, user) {
    this.token = token
    this.user = user
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },

  logout() {
    this.token = ''
    this.user = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }
})
