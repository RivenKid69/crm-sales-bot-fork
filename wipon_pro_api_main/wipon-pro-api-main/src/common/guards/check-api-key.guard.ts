import { CanActivate, ExecutionContext, HttpException, Injectable, UnauthorizedException } from '@nestjs/common';
import { Observable } from 'rxjs';
import { UserDao } from '../dao/user.dao';
import { DeviceDao } from '../dao/device.dao';
import { Request } from 'express';
import * as crc32 from 'locutus/php/strings/crc32';
import appConfig from '../../config/app.config';
import { md5 } from '../utils/md5';
import * as substr from 'locutus/php/strings/substr';

@Injectable()
export class CheckApiKeyGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean | Promise<boolean> | Observable<boolean> {
    const req = context.switchToHttp().getRequest();
    if (!req.user) throw new UnauthorizedException();
    return this.validateApiKey(req, req.user, req.headers['api-key']);
  }

  private async validateApiKey(req: Request, user: UserDao, apiKey: string): Promise<boolean> {
    let devices: DeviceDao[] | null = null;
    const foundUser = await UserDao.findOne({ where: { id: user.id }, relations: ['devices'] });
    if (foundUser) devices = foundUser.devices;
    // const isValidApiKey = this.checkIsApiKeyValid(apiKey);
    // if (!isValidApiKey) {
    //   throw new HttpException(this.getWrongResponse(), 200);
    // }

    if (!devices || !devices.length) {
      throw new HttpException('Подписка истекла или отсутствует', 400);
    }

    // let isValid = false;
    // console.log(devices);
    // devices?.forEach((device) => {
    //   const generatedApiKey = this.generateApiKey(req, device.device_code);
    //   const firstCompare = this.substrCompare(apiKey, generatedApiKey, 0, 32, true);
    //   const secondCompare = this.substrCompare(`0${apiKey}`, generatedApiKey, 0, 32, true);
    //   if (firstCompare === 0 || secondCompare === 0) {
    //     isValid = true;
    //   }
    // });
    //
    // if (!isValid) {
    //   throw new HttpException(this.getWrongResponse(), 200);
    // }
    return true;
  }

  private generateApiKey(request: Request, deviceCode: string) {
    const path = request.url;
    const bodyCrc32 = this.toHex(crc32(request.body));
    const key = appConfig['api-key'];
    const deviceCodeCRC32 = this.toHex(crc32(deviceCode));
    return md5(`${path}::body::${bodyCrc32}::key::${key}::device_code::${deviceCodeCRC32}`);
  }

  toHex(number) {
    if (number < 0) {
      number = 0xffffffff + number + 1;
    }
    return parseInt(number, 10).toString(16);
    // return ('0' + Number(d).toString(16)).slice(-2).toUpperCase();
  }

  private substrCompare(mainStr, str, offset, length, caseInsensitivity) {
    if (!offset && offset !== 0) {
      throw new Error('Missing offset for substr_compare()');
    }
    if (offset < 0) {
      offset = mainStr.length + offset;
    }
    if (length && length > mainStr.length - offset) {
      return false;
    }
    length = length || mainStr.length - offset;
    mainStr = substr(mainStr, offset, length);
    str = substr(str, 0, length);
    if (caseInsensitivity) {
      mainStr = (mainStr + '').toLowerCase();
      str = (str + '').toLowerCase();
      if (mainStr === str) {
        return 0;
      }
      return mainStr > str ? 1 : -1;
    }
    return mainStr === str ? 0 : mainStr > str ? 1 : -1;
  }

  private getWrongResponse() {
    return {
      item: {
        product_code: 'Для корректной работы обновите приложение с сайта',
        status: 'fake',
      },
      created_at: new Date().toLocaleString('ru-RU', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }),
    };
  }

  private checkIsApiKeyValid(apiKey): boolean {
    if (!apiKey) return false;
    if (typeof apiKey !== 'string') return false;
    if (!apiKey.match(/^[0-9a-zA-Z]+$/gi)) return false;
    if (apiKey.length < 32) return false;
    return true;
  }
}
