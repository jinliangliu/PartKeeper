<template>
  <div class="page-card">
    <div class="page-header">
      <div>
        <div class="title">分类管理</div>
        <div class="subtitle">树形多级分类，用于组织与筛选物料</div>
      </div>
      <el-tag type="info" effect="plain" round>共 {{ totalCount }} 个分类</el-tag>
    </div>

    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索分类名称"
        clearable
        :prefix-icon="Search"
        style="width: 260px"
      />
      <div class="spacer" />
      <el-button v-if="authStore.isAdmin" type="primary" :icon="Plus" @click="openCreate(null)">
        新增根分类
      </el-button>
    </div>

    <el-empty v-if="filteredTree.length === 0" description="没有匹配的分类" />

    <el-tree
      v-else
      :key="keyword"
      :data="filteredTree"
      node-key="id"
      default-expand-all
      :expand-on-click-node="false"
      :props="{ label: 'name', children: 'children' }"
    >
      <template #default="{ data }">
        <div class="tree-node">
          <span class="node-label">
            <el-icon class="node-icon" :class="{ folder: data.children?.length }">
              <Folder v-if="data.children?.length" />
              <Document v-else />
            </el-icon>
            <span class="name">{{ data.name }}</span>
            <el-tag
              v-if="data.children?.length"
              size="small"
              type="info"
              effect="plain"
              round
            >
              {{ data.children.length }}
            </el-tag>
          </span>
          <span v-if="authStore.isAdmin" class="actions">
            <el-button link type="primary" :icon="Plus" @click.stop="openCreate(data)">子分类</el-button>
            <el-button link type="primary" :icon="Edit" @click.stop="openEdit(data)">编辑</el-button>
            <el-button link type="danger" :icon="Delete" @click.stop="handleDelete(data)">删除</el-button>
          </span>
        </div>
      </template>
    </el-tree>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑分类' : '新增分类'" width="420px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px" @submit.prevent="save">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item v-if="!editingId" label="父级">
          <el-input :model-value="parentName" disabled />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Folder, Document, Plus, Edit, Delete, Search } from '@element-plus/icons-vue'
import http from '../api'
import { authStore } from '../stores/auth'

const tree = ref([])
const keyword = ref('')
const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const parentName = ref('（根分类）')
const formRef = ref()
const form = reactive({ name: '', parent_id: null })
const rules = { name: [{ required: true, message: '请输入分类名称', trigger: 'blur' }] }

function countNodes(nodes) {
  return nodes.reduce((sum, n) => sum + 1 + countNodes(n.children || []), 0)
}

const totalCount = computed(() => countNodes(tree.value))

function filterTree(nodes, kw) {
  const lower = kw.trim().toLowerCase()
  if (!lower) return nodes
  const result = []
  for (const node of nodes) {
    const selfMatch = node.name.toLowerCase().includes(lower)
    const childMatches = filterTree(node.children || [], lower)
    if (selfMatch) {
      result.push({ ...node, children: node.children })
    } else if (childMatches.length) {
      result.push({ ...node, children: childMatches })
    }
  }
  return result
}

const filteredTree = computed(() => filterTree(tree.value, keyword.value))

async function load() {
  const res = await http.get('/categories')
  tree.value = res.data
}

function openCreate(parent) {
  editingId.value = null
  form.name = ''
  form.parent_id = parent ? parent.id : null
  parentName.value = parent ? parent.name : '（根分类）'
  dialogVisible.value = true
}

function openEdit(data) {
  editingId.value = data.id
  form.name = data.name
  form.parent_id = data.parent_id
  dialogVisible.value = true
}

async function save() {
  await formRef.value.validate()
  saving.value = true
  try {
    if (editingId.value) {
      await http.put(`/categories/${editingId.value}`, { name: form.name })
      ElMessage.success('更新成功')
    } else {
      await http.post('/categories', form)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function handleDelete(data) {
  await ElMessageBox.confirm(`确定删除分类「${data.name}」吗？`, '警告', { type: 'warning' })
  await http.delete(`/categories/${data.id}`)
  ElMessage.success('删除成功')
  load()
}

onMounted(load)
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
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

.tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 3px 8px 3px 0;
  border-radius: 4px;
}

.tree-node:hover {
  background: #f5f7fa;
}

.node-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.node-icon {
  color: #909399;
}

.node-icon.folder {
  color: #e6a23c;
}

.name {
  font-size: 14px;
}

.actions {
  display: inline-flex;
  gap: 2px;
}
</style>
