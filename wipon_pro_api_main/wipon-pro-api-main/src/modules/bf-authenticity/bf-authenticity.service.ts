import { CACHE_MANAGER, HttpException, Inject, Injectable } from '@nestjs/common';
import appConfig from '../../config/app.config';
import bfConfig from '../../config/bf.config';
import { HttpService } from '@nestjs/axios';
import { FindOrCreateProductUseCase } from '../products/domain/use-cases/find-or-create-product.use-case';
import { ItemDao } from '../../common/dao/item.dao';
import { ProductDao } from '../../common/dao/product.dao';
import { createCustomLogger } from '../../common/logger/request-logger';
import { DoomguyService } from '../../common/services/doomguy/doomguy.service';
import { Cache } from 'cache-manager';
import * as https from 'https';
import * as substr from 'locutus/php/strings/substr';

type bfRequestParamsType = {
  Pdf417?: string|null,
  Bin?: string|null,
  ShopLicenseNumber?: string|null,
  Ukm?: string|null,
};

const oneDayInSecs = 86400;

@Injectable()
export class BfAuthenticityService {
  protected item;
  protected info;
  protected baseBfUrl = 'https://alcotrack-ukm-shops-api.qoldau.kz';
  protected kgdWiponUrl = 'https://kgd.router.wiponapp.com:5010';
  protected response;
  private name = 'src';

  constructor(
    private httpService: HttpService,
    private readonly findOrCreateProduct: FindOrCreateProductUseCase,
    private readonly doomguyService: DoomguyService,
    @Inject(CACHE_MANAGER) private cacheManager: Cache,
  ) {}

  async requestBfProductForItem(item: ItemDao): Promise<ProductDao | null> {
    const params = this.prepareBfRequestParams(item);
    if (!params) return null;

    this.item = item;
    let response;
    if (appConfig.environment === 'production') {
      response = await this.sendBfRequest(params);
    }

    if (!response || !this.isResponseValid(response)) return null;
    this.response = response;
    const info = this.parseBfProductInfo();

    if (!info) return null;
    this.info = info;

    const product = await this.findOrCreateProduct.handle(info.name, info.organization, info.type);
    this.updateItemInfo();
    return product;
  }

  // async requestProductForItem(item: ItemDao, isOldType = true): Promise<ProductDao | null> {
  //   const params = this.prepareBfRequestParams(item);
  //   if (!params) return null;
  //
  //   this.item = item;
  //   const response = await this.sendRequest(params);
  //
  //   if (!response || !this.isResponseValid(response)) return null;
  //   this.response = response;
  //   const info = this.parseBfProductInfo();
  //
  //   if (!info) return null;
  //   this.info = info;
  //
  //   const product = await this.findOrCreateProduct.handle(info.name, info.organization, info.type);
  //   this.updateItemInfo();
  //   return product;
  // }

  // async sendRequest(params: bfRequestParamsType) {
  //   const env = appConfig.environment;
  //   const logger = createCustomLogger('info', `${this.name}_requests`);
  //   const requestUrl = params.guid ? `${this.kgdWiponUrl}/guid` : this.kgdWiponUrl;
  //   try {
  //     const response = await this.httpService.axiosRef.post(requestUrl, params, {
  //       timeout: 5000,
  //     });
  //
  //     // eslint-disable-next-line @typescript-eslint/ban-ts-comment
  //     // @ts-ignore
  //     const responseBody = response.data?.items;
  //     logger.log('info', {
  //       requestUrl,
  //       request: { method: 'POST', header: 'Content-type: application/json', content: params },
  //       response: responseBody,
  //     });
  //     return responseBody || '<no response>';
  //     // $responseBody = $response ? $response->getBody()->getContents() : "<no response>";
  //   } catch (e) {
  //     const errorResponse = e.response;
  //     const responseStatus = errorResponse ? errorResponse.status : 'Недоступен';
  //     const responseBody = errorResponse ? errorResponse.data : 'no response';
  //     const msg = errorResponse ? errorResponse.data?.message : 'Empty message';
  //     logger.log('info', {
  //       requestUrl,
  //       request: { method: 'POST', header: 'Content-type: application/json', content: params },
  //       response: { statusCode: responseStatus, body: responseBody },
  //     });
  //     if (env !== 'testing') {
  //       await this.doomguyService.commitRage(
  //         `Сервис КГД не доступен! (HTTP Status: ${responseStatus}`,
  //         msg,
  //         '#kgd_router',
  //       );
  //     }
  //     throw new HttpException('SRC service unavailable', 424);
  //   }
  // }

  async sendBfRequest(params, tries = 0) {
    const env = appConfig.environment;
    const requestUrl = this.baseBfUrl + '/Api/GetUkmInfo';
    const token = bfConfig.token_key;

    const headers = {
      Authorization: `Bearer ${token}`,
    };
    try {
      const agent = new https.Agent({ rejectUnauthorized: false });
      const response = await this.httpService.axiosRef.post(requestUrl, params, {
        headers,
        timeout: 10000,
        httpsAgent: agent,
      });

      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      const responseBody = response.data;
      // logger.log('info', {
      //   requestUrl,
      //   request: { method: 'POST', header: 'Content-type: application/json', content: params },
      //   response: responseBody,
      // });
      return responseBody || null;
    } catch (e) {
      const errorResponse = e.response;
      const status = errorResponse ? errorResponse.status : 'Недоступен';
      const responseBody = errorResponse ? errorResponse.data : 'no response';
      const msg = errorResponse ? errorResponse.data?.message : 'Empty message';

      if (tries < 3) {
        tries++;
        return await this.sendBfRequest(params, tries);
      }

      const logger = createCustomLogger('info', `${this.name}_requests`);

      logger.log('info', {
        requestUrl,
        request: { method: 'POST', header: 'Content-type: application/json', content: params },
        response: { statusCode: status, body: responseBody },
      });

      if (env !== 'testing') {
        await this.doomguyService.commitRage(`Сервис КГД не доступен! (HTTP Status: ${status}`, msg, '#kgd_router');
      }

      throw new HttpException('Ведутся технические работы, попробуйте позднее', 424);
    }
  }

  prepareBfRequestParams(item: ItemDao): null | bfRequestParamsType {
    let params = {
      Pdf417: null,
      Bin: null,
      ShopLicenseNumber: '-',
      Ukm: '',
    };

    if (item.excise_code) {
      params.Ukm = item.excise_code.split(' ')[0];
      return params;
    }

    if (item.serial_number) {
      params.Ukm = item.serial_number;
      return params;
    }
    return null;
  }

  protected isResponseValid(response) {
    return !!response?.ProductName;
  }

  protected parseBfProductInfo() {
    const item = this.response;
    if (!item) return null;

    let productName = item.ProductName;
    if (!productName) return null;

    const productCapacity = String(item.Volume).trim();
    const productGroup = String(item.ProductGroup).trim();
    const organizationName = String(item.OrgReceivedUkmName).trim();

    let bottlingDate: string | null = String(item.UkmProducedDate).trim();
    // Check for invalid/default dates (1970-01-01 or 0001-01-01, with or without time)
    if (bottlingDate.startsWith('1970-01-01') || bottlingDate.startsWith('0001-01-01')) {
      bottlingDate = null;
    }

    if (bottlingDate && bottlingDate.includes('null')) {
      bottlingDate = null;
    }

    if (productCapacity) {
      productName += ` ${productCapacity} л.`;
    }

    return {
      name: productName,
      type: productGroup,
      organization: organizationName,
      bottlingDate,
    };
  }


  updateItemInfo() {
    let bottledAt = this.info.bottlingDate ? this.info.bottlingDate : null;
    if (bottledAt) {
      // Handle ISO 8601 format: "YYYY-MM-DDTHH:mm:ss" or "YYYY-MM-DDTHH:mm:ss.sss"
      // Extract date part (before 'T' or before '.')
      const tPos = bottledAt.indexOf('T');
      if (tPos !== -1) {
        bottledAt = substr(bottledAt, 0, tPos);
      } else {
        // Fallback: check for dot (old format)
        const dotPos = bottledAt.lastIndexOf('.');
        if (dotPos !== -1) {
          bottledAt = substr(bottledAt, 0, dotPos);
        }
      }
    }
    this.item.bottledAt = bottledAt;
  }
}
