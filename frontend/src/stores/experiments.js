import { defineStore } from 'pinia'
import { ref } from 'vue'
import { queryExperiments, checkSynthesis, verifyMaterial } from '@/api/experiments'

export const useExperimentsStore = defineStore('experiments', () => {
  const records = ref([])
  const synthesisResult = ref(null)
  const verifyResult = ref(null)
  const loading = ref(false)

  async function query(params) {
    loading.value = true
    try {
      const res = await queryExperiments(params)
      records.value = res.records || []
      return res
    } finally {
      loading.value = false
    }
  }

  async function check(smiles) {
    loading.value = true
    try {
      synthesisResult.value = await checkSynthesis({ smiles })
      return synthesisResult.value
    } finally {
      loading.value = false
    }
  }

  async function verify(smiles, propertyName) {
    loading.value = true
    try {
      verifyResult.value = await verifyMaterial({ smiles, property_name: propertyName })
      return verifyResult.value
    } finally {
      loading.value = false
    }
  }

  return { records, synthesisResult, verifyResult, loading, query, check, verify }
})
