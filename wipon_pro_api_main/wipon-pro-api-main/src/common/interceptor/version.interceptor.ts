import { CallHandler, ExecutionContext, Injectable, NestInterceptor } from '@nestjs/common';
import { Observable } from 'rxjs';
import { Response } from 'express';
import {
  MOBILE_VERSION_KEY_IN_HEADER,
  DESKTOP_VERSION_KEY_IN_HEADER,
  MOBILE_CURRENT_VERSION,
  DESKTOP_CURRENT_VERSION,
} from '../../config/version.config';

@Injectable()
export class VersionInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler<any>): Observable<any> | Promise<Observable<any>> {
    const response: Response = context.switchToHttp().getResponse();
    response.setHeader(MOBILE_VERSION_KEY_IN_HEADER, MOBILE_CURRENT_VERSION);
    response.setHeader(DESKTOP_VERSION_KEY_IN_HEADER, DESKTOP_CURRENT_VERSION);
    return next.handle();
  }
}
