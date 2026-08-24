<template>
  <div class="page-card">
    <div class="toolbar">
      <el-input
        v-model="query.keyword"
        placeholder="搜索名称 / 值 / 封装 / 品牌"
        clearable
        style="width: 260px"
        @keyup.enter="load"
        @clear="load"
      />
      <el-select v-model="query.category_id" placeholder="分类" clearable style="width: 160px" @change="load">
        <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
      </el-select>
      <el-button type="primary" @click="load">查询</el-button>
      <div class="spacer" />
      <el-button v-if="authStore.isAdmin" @click="openBom">BOM 导入</el-button>
      <el-button v-if="authStore.isAdmin" type="success" @click="openCreate">新增物料</el-button>
    </div>

    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column prop="value" label="值" min-width="90" />
      <el-table-column prop="package" label="封装" width="90" />
      <el-table-column prop="brand" label="品牌" width="100" />
      <el-table-column prop="category" label="分类" width="100" />
      <el-table-column label="库存" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="row.current_stock <= row.min_stock ? 'danger' : 'success'">
            {{ row.current_stock }} {{ row.unit }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="min_stock" label="最低库存" width="90" align="center" />
      <el-table-column prop="location" label="库位" width="100" />
      <el-table-column prop="supplier" label="供应商" width="120" />
      <el-table-column v-if="authStore.isAdmin" label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row.id)">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.per_page"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="load"
      />
    </div>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑物料' : '新增物料'" width="640px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="名称" prop="name"><el-input v-model="form.name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="值"><el-input v-model="form.value" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="封装"><el-input v-model="form.package" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="精度"><el-input v-model="form.tolerance" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="品牌"><el-input v-model="form.brand" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="单位">
              <el-input v-model="form.unit" placeholder="个" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="分类">
              <el-select v-model="form.category_id" placeholder="选择分类" clearable style="width: 100%">
                <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="库位">
              <el-select v-model="form.location_id" placeholder="选择库位" clearable style="width: 100%">
                <el-option v-for="l in locations" :key="l.id" :label="l.name" :value="l.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="供应商">
              <el-select v-model="form.supplier_id" placeholder="选择供应商" clearable style="width: 100%">
                <el-option v-for="s in suppliers" :key="s.id" :label="s.name" :value="s.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最低库存">
              <el-input-number v-model="form.min_stock" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col v-if="!editingId" :span="12">
            <el-form-item label="当前库存">
              <el-input-number v-model="form.current_stock" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="Datasheet">
              <el-input v-model="form.datasheet_url" placeholder="数据手册链接" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="bomDialogVisible" title="BOM 导入" width="860px">
      <el-alert
        title="支持常见 EDA 导出的 CSV 物料清单"
        description="表头需包含“值/Value”列，建议同时包含“封装/Package”和“数量/Qty”。系统会与现有物料匹配，标出缺失与缺口。"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />

      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        accept=".csv"
        :on-change="handleBomFileChange"
        :on-remove="handleBomFileRemove"
      >
        <div class="el-upload__text">将 CSV 文件拖到此处，或 <em>点击选择文件</em></div>
      </el-upload>

      <template v-if="bomResult">
        <div class="bom-summary">
          <el-tag>共 {{ bomResult.summary.total_lines }} 行</el-tag>
          <el-tag type="success">已匹配 {{ bomResult.summary.matched_lines }}</el-tag>
          <el-tag type="warning">缺失物料 {{ bomResult.summary.missing_lines }}</el-tag>
          <el-tag type="danger">总缺口 {{ bomResult.summary.total_shortage_qty }}</el-tag>
        </div>

        <el-table :data="bomResult.lines" border size="small" max-height="360">
          <el-table-column prop="row" label="行" width="50" />
          <el-table-column prop="designator" label="位号" width="100" />
          <el-table-column prop="value" label="值" min-width="110" />
          <el-table-column prop="package" label="封装" width="100" />
          <el-table-column prop="quantity" label="数量" width="70" align="center" />
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.matched_id" type="success" size="small">已匹配</el-tag>
              <el-tag v-else type="warning" size="small">缺失</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="current_stock" label="当前库存" width="90" align="center" />
          <el-table-column label="缺口" width="80" align="center">
            <template #default="{ row }">
              <span :class="{ 'text-danger': row.shortage > 0 }">{{ row.shortage }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="matched_name" label="匹配物料" min-width="130" />
        </el-table>
      </template>

      <template #footer>
        <el-button @click="closeBom">取消</el-button>
        <el-button type="primary" :loading="bomLoading" @click="parseBom">解析预览</el-button>
        <el-button
          v-if="bomResult && authStore.isAdmin"
          type="success"
          :loading="bomApplying"
          @click="applyBom"
        >
          创建缺失物料
        </el-button>
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
const total = ref(0)
const query = reactive({ page: 1, per_page: 20, keyword: '', category_id: null })

const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref()
const form = reactive({
  name: '', value: '', package: '', tolerance: '', brand: '', unit: '个',
  category_id: null, location_id: null, supplier_id: null,
  min_stock: 0, current_stock: 0, datasheet_url: ''
})
const rules = { name: [{ required: true, message: '请输入物料名称', trigger: 'blur' }] }

const categoryOptions = ref([])
const suppliers = ref([])
const locations = ref([])

const bomDialogVisible = ref(false)
const bomFile = ref(null)
const bomLoading = ref(false)
const bomApplying = ref(false)
const bomResult = ref(null)

function flattenCategories(nodes, depth = 0, out = []) {
  for (const node of nodes) {
    out.push({ value: node.id, label: `${'　'.repeat(depth)}${node.name}` })
    if (node.children?.length) {
      flattenCategories(node.children, depth + 1, out)
    }
  }
  return out
}

async function loadMeta() {
  const [catRes, supRes, locRes] = await Promise.all([
    http.get('/categories'),
    http.get('/suppliers'),
    http.get('/locations')
  ])
  categoryOptions.value = flattenCategories(catRes.data)
  suppliers.value = supRes.data
  locations.value = locRes.data
}

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, per_page: query.per_page }
    if (query.keyword) params.keyword = query.keyword
    if (query.category_id) params.category_id = query.category_id
    const res = await http.get('/components', { params })
    items.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function resetForm() {
  Object.assign(form, {
    name: '', value: '', package: '', tolerance: '', brand: '', unit: '个',
    category_id: null, location_id: null, supplier_id: null,
    min_stock: 0, current_stock: 0, datasheet_url: ''
  })
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

async function openEdit(id) {
  const res = await http.get(`/components/${id}`)
  Object.assign(form, res.data)
  editingId.value = id
  dialogVisible.value = true
}

async function save() {
  await formRef.value.validate()
  saving.value = true
  try {
    if (editingId.value) {
      await http.put(`/components/${editingId.value}`, form)
      ElMessage.success('更新成功')
    } else {
      await http.post('/components', form)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  await ElMessageBox.confirm(`确定删除物料「${row.name}」吗？`, '警告', { type: 'warning' })
  await http.delete(`/components/${row.id}`)
  ElMessage.success('删除成功')
  load()
}

function openBom() {
  bomFile.value = null
  bomResult.value = null
  bomDialogVisible.value = true
}

function closeBom() {
  bomDialogVisible.value = false
}

function handleBomFileChange(file) {
  bomFile.value = file.raw
  bomResult.value = null
}

function handleBomFileRemove() {
  bomFile.value = null
  bomResult.value = null
}

async function parseBom() {
  if (!bomFile.value) {
    ElMessage.warning('请先选择 CSV 文件')
    return
  }
  const formData = new FormData()
  formData.append('file', bomFile.value)
  bomLoading.value = true
  try {
    const res = await http.post('/bom/import', formData)
    bomResult.value = res.data
  } finally {
    bomLoading.value = false
  }
}

async function applyBom() {
  if (!bomFile.value) return
  const formData = new FormData()
  formData.append('file', bomFile.value)
  bomApplying.value = true
  try {
    const res = await http.post('/bom/apply', formData)
    ElMessage.success(`已创建 ${res.data.created} 条缺失物料`)
    closeBom()
    load()
  } finally {
    bomApplying.value = false
  }
}

onMounted(() => {
  loadMeta()
  load()
})
</script>

<style scoped>
.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.bom-summary {
  display: flex;
  gap: 8px;
  margin: 16px 0;
}

.text-danger {
  color: #f56c6c;
  font-weight: 600;
}
</style>
