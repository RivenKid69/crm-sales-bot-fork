import { Injectable } from '@nestjs/common';
import { fileGetContents } from '../../utils/common';
import * as crypto from 'crypto';

@Injectable()
export class SslService {
  checkSign(data, str: string, filename: string, alg = 'SHA1') {
    const pubkey = fileGetContents(filename);
    const verifyer = crypto.createVerify(alg);
    verifyer.update(data);
    const res = verifyer.verify(pubkey, str, 'base64');
    return res;
  }
}
