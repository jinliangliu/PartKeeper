<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">物料管理系统</div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#001529"
        text-color="rgba(255,255,255,0.75)"
        active-text-color="#fff"
      >
        <el-menu-item index="/dashboard">仪表盘</el-menu-item>
        <el-menu-item index="/components">物品管理</el-menu-item>
        <el-menu-item index="/categories">分类管理</el-menu-item>
        <el-menu-item index="/suppliers">供应商管理</el-menu-item>
        <el-menu-item index="/locations">库位管理</el-menu-item>
        <el-menu-item index="/boms">BOM 管理</el-menu-item>
        <el-menu-item index="/stock-in">入库操作</el-menu-item>
        <el-menu-item index="/stock-out">出库操作</el-menu-item>
        <el-menu-item index="/transactions">库存流水</el-menu-item>
        <el-menu-item index="/low-stock">低库存预警</el-menu-item>
        <el-menu-item index="/statistics">统计分析</el-menu-item>
        <el-menu-item index="/utility-bills">生活缴费</el-menu-item>
        <el-menu-item index="/expenses">家庭开支</el-menu-item>
        <el-menu-item v-if="authStore.isAdmin" index="/users">用户管理</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="page-title">{{ $route.meta.title }}</div>
        <div class="user">
          <el-tag size="small" :type="authStore.isAdmin ? 'danger' : 'info'">
            {{ authStore.isAdmin ? '管理员' : '普通用户' }}
          </el-tag>
          <span class="username">{{ authStore.user?.username }}</span>
          <el-button link type="danger" @click="handleLogout">退出</el-button>
        </div>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { authStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => route.path)

async function handleLogout() {
  await ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
  authStore.logout()
  ElMessage.success('已退出登录')
  router.push('/login')
}
</script>

<style scoped>
.layout {
  height: 100%;
}

.aside {
  background: #001529;
}

.logo {
  height: 60px;
  line-height: 60px;
  text-align: center;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
}

.aside :deep(.el-menu) {
  border-right: none;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
}

.user {
  display: flex;
  align-items: center;
  gap: 10px;
}

.main {
  background: #f5f7fa;
}
</style>
