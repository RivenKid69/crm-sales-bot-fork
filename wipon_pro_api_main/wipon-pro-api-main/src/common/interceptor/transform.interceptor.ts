import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { classToPlain } from 'class-transformer';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

@Injectable()
export class TransformInterceptor implements NestInterceptor {
  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    return next.handle().pipe(
      map((data) =>
        classToPlain({
          data: data,
          // data: data.result ?? data,
          // meta: data.meta ?? undefined,
        }),
      ),
    );
  }
}
