<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="title">物料管理系统</h2>
      <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleLogin">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" size="large" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            size="large"
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="submit" :loading="loading" @click="handleLogin">
          登 录
        </el-button>
      </el-form>
      <p class="hint">账号由管理员分配；忘记密码请找维护人员重置</p>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '../api'
import { authStore } from '../stores/auth'

const router = useRouter()
const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function handleLogin() {
  await formRef.value.validate()
  loading.value = true
  try {
    const res = await http.post('/auth/login', form)
    authStore.setAuth(res.data.token, res.data.user)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1677ff 0%, #001529 100%);
}

.login-card {
  width: 380px;
  padding: 16px 8px;
}

.title {
  text-align: center;
  margin-bottom: 24px;
}

.submit {
  width: 100%;
}

.hint {
  text-align: center;
  color: #999;
  font-size: 12px;
  margin-top: 12px;
}
</style>
