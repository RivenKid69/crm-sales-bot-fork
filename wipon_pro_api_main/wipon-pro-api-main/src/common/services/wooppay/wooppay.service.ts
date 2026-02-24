// import { Injectable } from '@nestjs/common';
// import { createClientAsync } from 'soap';
// import appConfig from '../../../config/app.config';
//
// @Injectable()
// export class WooppayService {
//   private client;
//
//   constructor() {
//     this.client = await createClientAsync(appConfig.wooppay.wsdl);
//   }
//
//   cashGetOperationData($operationId, session: any = null) {
//     if (session === null) {
//     }
//     return 1;
//   }
//
//   async coreLogin() {
//     const result: any = {};
//     try {
//       const response = await this.client.core_login({
//         username: appConfig.wooppay.login,
//         password: appConfig.wooppay.password,
//         captcha: null,
//       });
//       result.session = response.session; // (Или response.response.session)
//       return result;
//     } catch (e) {
//       result.error_code = e?.response?.statusCode;
//       // $result['error_code'] = $response->error_code; В PHP вот так
//     }
//   }
// }
