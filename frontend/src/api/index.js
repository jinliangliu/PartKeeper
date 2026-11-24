import axios from 'axios'
import { ElMessage } from 'element-plus'
import { authStore } from '../stores/auth'
import router from '../router'

const http = axios.create({
  baseURL: '/api',
  timeout: 15000
})

http.interceptors.request.use((config) => {
  const token = authStore.token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => {
    const body = response.data
    if (body && body.code !== undefined && body.code !== 200) {
      ElMessage.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  (error) => {
    const status = error.response?.status
    const message = error.response?.data?.message || error.message || '网络错误'
    // 登录接口的 401 是「账号或密码错误」，不是会话过期。
    // 不能清 token、不能跳转，更不能显示成「登录已过期」——那会让人以为只是刷新一下就好。
    if (status === 401 && String(error.config?.url || '').includes('/auth/login')) {
      ElMessage.error(message || '用户名或密码错误')
      return Promise.reject(error)
    }
    if (status === 401) {
      authStore.logout()
      ElMessage.error('登录已过期，请重新登录')
      if (router.currentRoute.value.path !== '/login') {
        router.push('/login')
      }
    } else {
      ElMessage.error(message)
    }
    return Promise.reject(error)
  }
)

export default http
