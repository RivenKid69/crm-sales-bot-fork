import { CanActivate, ExecutionContext, ForbiddenException, Injectable } from '@nestjs/common';
import { Observable } from 'rxjs';
import { Request } from 'express';
import appConfig from '../../config/app.config';

@Injectable()
export class TransactionGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean | Promise<boolean> | Observable<boolean> {
    const request = context.switchToHttp().getRequest();
    return this.validateToken(request);
  }

  private async validateToken(request: Request): Promise<boolean> {
    const token = appConfig.transactionToken;
    if (!token) return true;
    const authorization = request.headers.authorization;
    if (!authorization) throw new ForbiddenException();
    const transactionToken = authorization.split(' ')[1];
    if (!transactionToken) throw new ForbiddenException();
    return String(transactionToken) === String(token);
  }
}
