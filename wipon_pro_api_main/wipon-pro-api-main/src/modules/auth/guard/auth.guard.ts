import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { Observable } from 'rxjs';
import { FindUserByTokenUseCase } from '../../users/domain/use-cases/find-user-by-token.use-case';
import { Request } from 'express';

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(private readonly findUserByToken: FindUserByTokenUseCase) {}

  canActivate(context: ExecutionContext): boolean | Promise<boolean> | Observable<boolean> {
    const request = context.switchToHttp().getRequest();
    return this.validateUser(request);
  }

  private async validateUser(request: Request): Promise<boolean> {
    const authorization = request.headers.authorization;
    if (!authorization) throw new UnauthorizedException();
    const token = authorization.split(' ')[1];
    const user = await this.findUserByToken.handle(token);
    if (!user) throw new UnauthorizedException();
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore
    request.user = user;
    return true;
  }
}
