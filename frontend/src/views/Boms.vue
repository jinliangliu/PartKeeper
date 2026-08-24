<template>
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="title">BOM 管理</div>
        <div class="subtitle">维护常用物料清单（BOM），出库时可整单批量出库</div>
      </div>
    </div>

    <div class="toolbar">
      <div class="spacer" />
      <el-button v-if="authStore.isAdmin" type="primary" :icon="Plus" @click="openCreate">新建 BOM</el-button>
    </div>

    <el-table :data="boms" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column prop="description" label="说明" min-width="200" />
      <el-table-column prop="item_count" label="器件数" width="90" align="center" />
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column v-if="authStore.isAdmin" label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑 BOM' : '新建 BOM'" width="760px">
      <el-form :model="form" label-width="70px">
        <el-row :gutter="12">
          <el-col :span="10">
            <el-form-item label="名称" required>
              <el-input v-model="form.name" />
            </el-form-item>
          </el-col>
          <el-col :span="14">
            <el-form-item label="说明">
              <el-input v-model="form.description" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div class="add-row">
        <el-select
          v-model="newComponentId"
          filterable
          remote
          clearable
          :remote-method="searchComponents"
          :loading="searching"
          placeholder="搜索物料名称 / 值 / 封装"
          style="width: 300px"
        >
          <el-option v-for="c in componentOptions" :key="c.id" :label="c.label" :value="c.id" />
        </el-select>
        <el-input-number v-model="newQty" :min="1" style="width: 120px" />
        <el-button type="primary" plain :icon="Plus" @click="addItem">添加器件</el-button>
      </div>

      <el-table :data="form.items" border size="small" style="margin-top: 12px" max-height="360">
        <el-table-column label="物料" min-width="240">
          <template #default="{ row }">{{ row.label }}</template>
        </el-table-column>
        <el-table-column label="当前库存" width="110" align="center">
          <template #default="{ row }">{{ row.current_stock }} {{ row.unit }}</template>
        </el-table-column>
        <el-table-column label="数量" width="150" align="center">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="1" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" @click="removeItem($index)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>

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
import { Plus } from '@element-plus/icons-vue'
import http from '../api'
import { authStore } from '../stores/auth'

const loading = ref(false)
const saving = ref(false)
const searching = ref(false)
const boms = ref([])
const dialogVisible = ref(false)
const editingId = ref(null)
const componentOptions = ref([])
const newComponentId = ref(null)
const newQty = ref(1)

const form = reactive({ name: '', description: '', items: [] })

function formatTime(value) {
  return value ? value.replace('T', ' ').slice(0, 19) : ''
}

function componentLabel(c) {
  return `${c.name}${c.value ? ` · ${c.value}` : ''}${c.package ? ` · ${c.package}` : ''}`
}

async function load() {
  loading.value = true
  try {
    const res = await http.get('/boms')
    boms.value = res.data
  } finally {
    loading.value = false
  }
}

async function searchComponents(keyword = '') {
  searching.value = true
  try {
    const res = await http.get('/components', { params: { page: 1, per_page: 50, keyword } })
    componentOptions.value = res.data.items.map((c) => ({
      id: c.id,
      label: componentLabel(c),
      current_stock: c.current_stock,
      unit: c.unit
    }))
  } finally {
    searching.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.description = ''
  form.items = []
  newComponentId.value = null
  newQty.value = 1
  dialogVisible.value = true
  searchComponents('')
}

async function openEdit(row) {
  editingId.value = row.id
  const res = await http.get(`/boms/${row.id}`)
  const data = res.data
  form.name = data.name
  form.description = data.description || ''
  form.items = data.items.map((it) => ({
    component_id: it.component_id,
    label: componentLabel({ name: it.component_name, value: it.value, package: it.package }),
    current_stock: it.current_stock,
    unit: it.unit,
    quantity: it.quantity
  }))
  newComponentId.value = null
  newQty.value = 1
  dialogVisible.value = true
  searchComponents('')
}

function addItem() {
  if (!newComponentId.value) {
    ElMessage.warning('请先选择物料')
    return
  }
  const opt = componentOptions.value.find((c) => c.id === newComponentId.value)
  if (!opt) return
  if (form.items.some((it) => it.component_id === opt.id)) {
    ElMessage.warning('该物料已在列表中')
    return
  }
  form.items.push({
    component_id: opt.id,
    label: opt.label,
    current_stock: opt.current_stock,
    unit: opt.unit,
    quantity: newQty.value
  })
  newComponentId.value = null
  newQty.value = 1
}

function removeItem(index) {
  form.items.splice(index, 1)
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入 BOM 名称')
    return
  }
  const items = form.items.map((it) => ({ component_id: it.component_id, quantity: it.quantity }))
  saving.value = true
  try {
    if (editingId.value) {
      await http.put(`/boms/${editingId.value}`, { name: form.name, description: form.description })
      await http.put(`/boms/${editingId.value}/items`, { items })
      ElMessage.success('保存成功')
    } else {
      await http.post('/boms', { name: form.name, description: form.description, items })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除 BOM「${row.name}」吗？`, '警告', { type: 'warning' })
  await http.delete(`/boms/${row.id}`)
  ElMessage.success('删除成功')
  load()
}

onMounted(load)
</script>

<style scoped>
.page-header {
  margin-bottom: 16px;
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.subtitle {
  margin-top: 4px;
  color: #909399;
  font-size: 13px;
}

.add-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
