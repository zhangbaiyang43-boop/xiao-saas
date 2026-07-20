import { createStore } from 'vuex'

const store = createStore({
  state: {
    token: uni.getStorageSync('token') || '',
    customer: null
  },
  mutations: {
    SET_TOKEN(state, token) {
      state.token = token
      uni.setStorageSync('token', token)
    },
    SET_CUSTOMER(state, customer) {
      state.customer = customer
    },
    CLEAR_TOKEN(state) {
      state.token = ''
      state.customer = null
      uni.removeStorageSync('token')
    }
  },
  actions: {
    login({ commit }, token) {
      commit('SET_TOKEN', token)
    },
    logout({ commit }) {
      commit('CLEAR_TOKEN')
    },
    setCustomer({ commit }, customer) {
      commit('SET_CUSTOMER', customer)
    }
  },
  getters: {
    isLoggedIn: state => !!state.token,
    customer: state => state.customer
  }
})

export default store