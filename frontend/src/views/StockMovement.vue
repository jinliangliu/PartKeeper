<template>
  <div class="page-card movement">
    <el-alert
      :title="isIn ? '入库操作' : '出库操作'"
      :description="isIn ? '选择物料并填写数量，过账后将增加库存。' : '选择物料并填写数量，过账前会校验库存是否充足。'"
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
    />

    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" class="form">
      <el-form-item label="物料" prop="item_id">
        <el-select
          v-model="form.item_id"
          filterable
          remote
          :remote-method="searchComponents"
          :loading="searching"
          placeholder="输入名称 / 值 / 封装搜索"
          style="width: 420px"
          @change="handleComponentChange"
        >
          <el-option
            v-for="c in componentOptions"
            :key="c.id"
            :label="c.label"
            :value="c.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item v-if="selected" label="当前库存">
        <el-tag :type="selected.current_stock > 0 ? 'success' : 'info'">
          {{ selected.current_stock }} {{ selected.unit || '个' }}
        </el-tag>
      </el-form-item>

      <el-form-item label="数量" prop="quantity">
        <el-input-number v-model="form.quantity" :min="1" style="width: 180px" />
      </el-form-item>

      <el-form-item v-if="isIn" label="单价(元)">
        <el-input-number
          v-model="form.unit_price"
          :min="0"
          :precision="4"
          :step="0.01"
          style="width: 180px"
          placeholder="可选"
        />
        <span class="tip">可选，用于采购金额统计</span>
      </el-form-item>

      <el-form-item label="备注">
        <el-input v-model="form.note" type="textarea" :rows="2" maxlength="255" style="width: 420px" />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">
          {{ isIn ? '确认入库' : '确认出库' }}
        </el-button>
        <el-button v-if="!isIn" type="warning" @click="openBatch">按 BOM 批量出库</el-button>
        <el-button @click="reset">重置</el-button>
      </el-form-item>
    </el-form>

    <el-dialog v-model="batchDialogVisible" title="按 BOM 批量出库" width="780px">
      <el-alert
        title="选择 BOM 后自动载入物料清单，可在此表格中增删行、修改数量"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />

      <div class="batch-toolbar">
        <el-select
          v-model="selectedBomId"
          placeholder="选择 BOM"
          clearable
          style="width: 260px"
          @change="handleBomSelect"
        >
          <el-option v-for="b in bomOptions" :key="b.id" :label="`${b.name}（${b.item_count} 项）`" :value="b.id" />
        </el-select>
      </div>

      <div class="add-row">
        <el-select
          v-model="batchNewComponentId"
          filterable
          remote
          clearable
          :remote-method="searchComponents"
          :loading="searching"
          placeholder="添加额外物料"
          style="width: 300px"
        >
          <el-option v-for="c in componentOptions" :key="c.id" :label="c.label" :value="c.id" />
        </el-select>
        <el-input-number v-model="batchNewQty" :min="1" style="width: 120px" />
        <el-button type="primary" plain @click="addBatchRow">添加</el-button>
      </div>

      <el-table :data="batchRows" border size="small" style="margin-top: 12px" max-height="360">
        <el-table-column label="物料" min-width="240">
          <template #default="{ row }">{{ row.label }}</template>
        </el-table-column>
        <el-table-column label="当前库存" width="110" align="center">
          <template #default="{ row }">{{ row.current_stock }} {{ row.unit }}</template>
        </el-table-column>
        <el-table-column label="出库数量" width="160" align="center">
          <template #default="{ row }">
            <el-input-number v-model="row.quantity" :min="1" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" @click="removeBatchRow($index)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="batchDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchSaving" :disabled="!batchRows.length" @click="submitBatch">
          确认批量出库
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '../api'

const route = useRoute()
const isIn = computed(() => route.meta.mode === 'in')

const formRef = ref()
const searching = ref(false)
const submitting = ref(false)
const componentOptions = ref([])
const selected = ref(null)
const form = reactive({ item_id: null, quantity: 1, unit_price: null, note: '' })
const rules = {
  item_id: [{ required: true, message: '请选择物料', trigger: 'change' }],
  quantity: [{ required: true, message: '请输入数量', trigger: 'change' }]
}

const batchDialogVisible = ref(false)
const bomOptions = ref([])
const selectedBomId = ref(null)
const batchRows = ref([])
const batchNewComponentId = ref(null)
const batchNewQty = ref(1)
const batchSaving = ref(false)

async function searchComponents(keyword = '') {
  searching.value = true
  try {
    const res = await http.get('/components', { params: { page: 1, per_page: 50, keyword } })
    componentOptions.value = res.data.items.map((c) => ({
      id: c.id,
      current_stock: c.current_stock,
      unit: c.unit,
      label: `${c.name}${c.value ? ` · ${c.value}` : ''}${c.package ? ` · ${c.package}` : ''}`
    }))
  } finally {
    searching.value = false
  }
}

function handleComponentChange(id) {
  selected.value = componentOptions.value.find((c) => c.id === id) || null
}

function reset() {
  form.item_id = null
  form.quantity = 1
  form.unit_price = null
  form.note = ''
  selected.value = null
  formRef.value?.clearValidate()
}

async function submit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    const payload = {
      item_id: form.item_id,
      quantity: form.quantity,
      note: form.note
    }
    if (isIn.value && form.unit_price != null) {
      payload.unit_price = form.unit_price
    }
    const res = await http.post(`/transactions/${isIn.value ? 'in' : 'out'}`, payload)
    ElMessage.success(res.message || (isIn.value ? '入库成功' : '出库成功'))
    reset()
    searchComponents('')
  } finally {
    submitting.value = false
  }
}

async function openBatch() {
  batchDialogVisible.value = true
  selectedBomId.value = null
  batchRows.value = []
  batchNewComponentId.value = null
  batchNewQty.value = 1
  const res = await http.get('/boms')
  bomOptions.value = res.data
  searchComponents('')
}

async function handleBomSelect(id) {
  batchRows.value = []
  if (!id) return
  const res = await http.get(`/boms/${id}`)
  batchRows.value = res.data.items.map((it) => ({
    item_id: it.item_id,
    label: `${it.item_name}${it.value ? ` · ${it.value}` : ''}${it.package ? ` · ${it.package}` : ''}`,
    current_stock: it.current_stock,
    unit: it.unit,
    quantity: it.quantity
  }))
}

function addBatchRow() {
  if (!batchNewComponentId.value) {
    ElMessage.warning('请先选择物料')
    return
  }
  const opt = componentOptions.value.find((c) => c.id === batchNewComponentId.value)
  if (!opt) return
  if (batchRows.value.some((r) => r.item_id === opt.id)) {
    ElMessage.warning('该物料已在列表中')
    return
  }
  batchRows.value.push({
    item_id: opt.id,
    label: opt.label,
    current_stock: opt.current_stock,
    unit: opt.unit,
    quantity: batchNewQty.value
  })
  batchNewComponentId.value = null
  batchNewQty.value = 1
}

function removeBatchRow(index) {
  batchRows.value.splice(index, 1)
}

async function submitBatch() {
  if (!batchRows.value.length) return
  batchSaving.value = true
  try {
    const res = await http.post('/transactions/out-batch', {
      items: batchRows.value.map((r) => ({ item_id: r.item_id, quantity: r.quantity }))
    })
    ElMessage.success(res.message || '批量出库成功')
    batchDialogVisible.value = false
    batchRows.value = []
    selectedBomId.value = null
    searchComponents('')
  } finally {
    batchSaving.value = false
  }
}

onMounted(() => searchComponents(''))
</script>

<style scoped>
.movement {
  max-width: 760px;
}

.tip {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.batch-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.add-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
