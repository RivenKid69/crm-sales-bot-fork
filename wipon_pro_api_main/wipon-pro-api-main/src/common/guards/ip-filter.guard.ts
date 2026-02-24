import { CanActivate, ExecutionContext, HttpException, Injectable } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { Observable } from 'rxjs';
import appConfig from '../../config/app.config';
import ipFilterConfig from '../../config/ip-filter.config';

@Injectable()
export class IpFilterGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean | Promise<boolean> | Observable<boolean> {
    const request = context.switchToHttp().getRequest();
    const ip = request.ip;
    if (!ip) throw new HttpException('IP address is not set', 400);
    const env = appConfig.environment;
    const provider = this.reflector.get<string>('provider', context.getHandler());
    if (!provider) throw new HttpException('Provider has not been set', 500);
    if (env === 'production' && !ipFilterConfig[provider][env].includes(ip)) {
      throw new HttpException('Forbidden', 403);
    }
    return true;
  }
}
