// eslint-disable-next-line @typescript-eslint/no-var-requires
const Dotenv = require("dotenv-webpack");

module.exports = {
  configureWebpack: {
    plugins: [new Dotenv()],
  },

  css: {
    loaderOptions: {
      scss: {
        prependData: '@import "@/assets/style/base/_variables.scss";',
      },
    },
  },
};
