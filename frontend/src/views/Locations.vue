<template>
  <div class="page-card">
    <div class="toolbar">
      <div class="spacer" />
      <el-button v-if="authStore.isAdmin" type="success" @click="openCreate">新增库位</el-button>
    </div>

    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="库位编号" width="180" />
      <el-table-column prop="description" label="描述" min-width="240" />
      <el-table-column v-if="authStore.isAdmin" label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑库位' : '新增库位'" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="编号" prop="name"><el-input v-model="form.name" placeholder="如 A1-2" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api'
import { authStore } from '../stores/auth'

const loading = ref(false)
const saving = ref(false)
const items = ref([])
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref()
const form = reactive({ name: '', description: '' })
const rules = { name: [{ required: true, message: '请输入库位编号', trigger: 'blur' }] }

async function load() {
  loading.value = true
  try {
    const res = await http.get('/locations')
    items.value = res.data
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, { name: '', description: '' })
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  editingId.value = row.id
  Object.assign(form, row)
  dialogVisible.value = true
}

async function save() {
  await formRef.value.validate()
  saving.value = true
  try {
    if (editingId.value) {
      await http.put(`/locations/${editingId.value}`, form)
      ElMessage.success('更新成功')
    } else {
      await http.post('/locations', form)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除库位「${row.name}」吗？`, '警告', { type: 'warning' })
  await http.delete(`/locations/${row.id}`)
  ElMessage.success('删除成功')
  load()
}

onMounted(load)
</script>
