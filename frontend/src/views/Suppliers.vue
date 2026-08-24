<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索名称 / 联系人"
        clearable
        style="width: 220px"
        @keyup.enter="load"
        @clear="load"
      />
      <el-button type="primary" @click="load">查询</el-button>
      <div class="spacer" />
      <el-button v-if="authStore.isAdmin" type="success" @click="openCreate">新增供应商</el-button>
    </div>

    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="contact" label="联系人" width="100" />
      <el-table-column prop="phone" label="电话" width="130" />
      <el-table-column prop="address" label="地址" min-width="160" />
      <el-table-column prop="website" label="官网" min-width="160" />
      <el-table-column v-if="authStore.isAdmin" label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑供应商' : '新增供应商'" width="520px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="联系人"><el-input v-model="form.contact" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="form.phone" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="form.address" /></el-form-item>
        <el-form-item label="官网"><el-input v-model="form.website" /></el-form-item>
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
const keyword = ref('')
const items = ref([])
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref()
const form = reactive({ name: '', contact: '', phone: '', address: '', website: '' })
const rules = { name: [{ required: true, message: '请输入供应商名称', trigger: 'blur' }] }

async function load() {
  loading.value = true
  try {
    const res = await http.get('/suppliers', { params: keyword.value ? { keyword: keyword.value } : {} })
    items.value = res.data
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, { name: '', contact: '', phone: '', address: '', website: '' })
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
      await http.put(`/suppliers/${editingId.value}`, form)
      ElMessage.success('更新成功')
    } else {
      await http.post('/suppliers', form)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除供应商「${row.name}」吗？`, '警告', { type: 'warning' })
  await http.delete(`/suppliers/${row.id}`)
  ElMessage.success('删除成功')
  load()
}

onMounted(load)
</script>
